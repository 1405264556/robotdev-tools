"""ROS-free rosbag2 analysis engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore

from robotdev_tools.config import AnalysisConfig, ConfigInput, load_config
from robotdev_tools.gates import evaluate_gates
from robotdev_tools.models import (
    AnalysisResult,
    BagMetadata,
    OdometryMetrics,
    TopicMetrics,
)
from robotdev_tools.specialized import SpecializedAnalyzers, build_framework
from robotdev_tools.stats import OdometryAccumulator, TopicAccumulator, percentile

SCHEMA_VERSION = "1.1"
TOOL_VERSION = "0.3.0"
DEFAULT_SAMPLE_LIMIT = 20_000


class AnalysisError(RuntimeError):
    """Raised when a bag cannot be analyzed."""


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _default_typestore(config: AnalysisConfig | None) -> Any:
    if config is None or config.ros_distro is None:
        return None
    normalized = config.ros_distro.lower().removeprefix("ros2_")
    for store in Stores:
        if store.value.lower().removeprefix("ros2_") == normalized:
            return get_typestore(store)
    supported = ", ".join(store.value for store in Stores if store.value.startswith("ros2_"))
    raise AnalysisError(f"unsupported ros_distro {config.ros_distro!r}; choose one of: {supported}")


def _storage_format(path: Path) -> str:
    if path.suffix.lower() == ".mcap":
        return "mcap"
    if path.suffix.lower() == ".db3":
        return "sqlite3"
    if path.is_dir():
        if any(path.glob("*.mcap")):
            return "mcap"
        if any(path.glob("*.db3")):
            return "sqlite3"
    return "rosbag2"


def _reader_paths(path: Path) -> list[Path]:
    """Return storage files directly for robust Unicode and split-bag handling.

    On Windows, upstream metadata parsing uses the locale default encoding.
    Reading the raw storage files avoids that limitation and also lets AnyReader
    merge split bag files in timestamp order.
    """

    if not path.is_dir():
        return [path]
    storage_files = sorted((*path.glob("*.db3"), *path.glob("*.mcap")))
    return storage_files or [path]


def _vector(vector: Any) -> tuple[float, float, float]:
    return float(vector.x), float(vector.y), float(vector.z)


def _finalize_topic(
    accumulator: TopicAccumulator,
    bag_start_ns: int,
    config: AnalysisConfig | None,
) -> TopicMetrics:
    duration_s = 0.0
    if accumulator.minimum_ns is not None and accumulator.maximum_ns is not None:
        duration_s = max(0.0, (accumulator.maximum_ns - accumulator.minimum_ns) / 1e9)
    mean_rate = None
    if accumulator.count > 1 and duration_s > 0:
        mean_rate = (accumulator.count - 1) / duration_s
    median_delta_ms = percentile(accumulator.delta_sample.items, 0.5)
    median_rate = None
    if median_delta_ms is not None and median_delta_ms > 0:
        median_rate = 1000 / median_delta_ms
    threshold = None
    if config is not None and accumulator.name in config.topics:
        threshold = config.topics[accumulator.name].max_gap_ms
    gap_count, estimated = accumulator.gap_summary(threshold)
    timeline = sorted((value - bag_start_ns) / 1e9 for value in accumulator.timeline.items)
    return TopicMetrics(
        name=accumulator.name,
        message_type=accumulator.message_type,
        message_count=accumulator.count,
        observed_duration_s=_round(duration_s) or 0.0,
        mean_rate_hz=_round(mean_rate),
        median_rate_hz=_round(median_rate),
        jitter_ms=_round(accumulator.deltas_ms.stddev),
        max_gap_ms=_round(accumulator.deltas_ms.maximum),
        gap_count=gap_count,
        gap_count_estimated=estimated,
        duplicate_timestamps=accumulator.duplicate_timestamps,
        reversed_timestamps=accumulator.reversed_timestamps,
        sampled_points=len(accumulator.timeline.items),
        sample_limit=accumulator.sample_limit,
        timeline_s=timeline,
    )


def _finalize_odometry(
    accumulator: OdometryAccumulator,
    message_count: int,
    bag_start_ns: int,
) -> OdometryMetrics:
    displacement = None
    if accumulator.first_position is not None and accumulator.last_position is not None:
        displacement = math.dist(accumulator.first_position, accumulator.last_position)
    path = sorted(accumulator.trajectory.items, key=lambda value: value[0])
    return OdometryMetrics(
        topic=accumulator.topic,
        message_count=message_count,
        decoded_count=accumulator.decoded_count,
        decode_errors=accumulator.decode_errors,
        total_distance_m=_round(accumulator.total_distance_m),
        displacement_m=_round(displacement),
        mean_linear_speed_mps=_round(
            accumulator.linear_speeds.mean if accumulator.linear_speeds.count else None
        ),
        max_linear_speed_mps=_round(accumulator.linear_speeds.maximum),
        p95_linear_speed_mps=_round(percentile(accumulator.linear_sample.items, 0.95)),
        mean_angular_speed_rps=_round(
            accumulator.angular_speeds.mean if accumulator.angular_speeds.count else None
        ),
        max_angular_speed_rps=_round(accumulator.angular_speeds.maximum),
        p95_angular_speed_rps=_round(percentile(accumulator.angular_sample.items, 0.95)),
        max_acceleration_mps2=_round(accumulator.accelerations.maximum),
        max_position_jump_m=_round(accumulator.position_jumps.maximum),
        speed_violation_count=accumulator.speed_violation_count,
        acceleration_violation_count=accumulator.acceleration_violation_count,
        position_jump_count=accumulator.position_jump_count,
        sampled_points=len(path),
        sample_limit=accumulator.sample_limit,
        trajectory_x_m=[round(point[1], 6) for point in path],
        trajectory_y_m=[round(point[2], 6) for point in path],
        trajectory_time_s=[round((point[0] - bag_start_ns) / 1e9, 6) for point in path],
    )


def analyze_bag(
    path: str | Path,
    config: ConfigInput = None,
    *,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> AnalysisResult:
    """Analyze one ROS 2 bag and return metrics and quality-gate results.

    Args:
        path: rosbag2 directory, ``.db3`` file, or ``.mcap`` file.
        config: Versioned YAML path, mapping, or :class:`AnalysisConfig`.
        sample_limit: Maximum timing and trajectory points retained per stream.

    Raises:
        AnalysisError: If the input cannot be read or analyzed.
    """

    bag_path = Path(path).expanduser().resolve()
    if not bag_path.exists():
        raise AnalysisError(f"bag path does not exist: {bag_path}")
    if sample_limit < 10:
        raise AnalysisError("sample_limit must be at least 10")
    loaded_config = load_config(config)
    typestore = _default_typestore(loaded_config)
    reader_kwargs: dict[str, Any] = {}
    if typestore is not None:
        reader_kwargs["default_typestore"] = typestore

    warnings: list[str] = []
    accumulators: dict[str, TopicAccumulator] = {}
    odometry_accumulator: OdometryAccumulator | None = None
    odometry_topic: str | None = None
    specialized = SpecializedAnalyzers()
    decode_warning_counts: dict[str, int] = {}

    try:
        with AnyReader(_reader_paths(bag_path), **reader_kwargs) as reader:
            start_time_ns = int(reader.start_time)
            end_time_ns = int(reader.end_time)
            if end_time_ns < start_time_ns:
                start_time_ns = 0
                end_time_ns = 0
            connections = list(reader.connections)
            for connection in connections:
                current = accumulators.get(connection.topic)
                if current is None:
                    accumulators[connection.topic] = TopicAccumulator(
                        name=connection.topic,
                        message_type=connection.msgtype,
                        sample_limit=sample_limit,
                    )
                elif current.message_type != connection.msgtype:
                    warnings.append(
                        f"Topic {connection.topic} has multiple message types; "
                        f"using {current.message_type}."
                    )
                specialized.prepare(connection.topic, connection.msgtype)

            if loaded_config is not None and loaded_config.odometry is not None:
                odometry_topic = loaded_config.odometry.topic
            else:
                for connection in connections:
                    if connection.msgtype == "nav_msgs/msg/Odometry":
                        odometry_topic = connection.topic
                        break
            if odometry_topic is not None:
                odometry_accumulator = OdometryAccumulator(odometry_topic, sample_limit)

            for connection, timestamp_ns, rawdata in reader.messages():
                accumulator = accumulators[connection.topic]
                accumulator.add(int(timestamp_ns))
                specialized_topic = connection.topic in specialized.accumulators
                odometry_message = (
                    odometry_accumulator is not None and connection.topic == odometry_topic
                )
                if not specialized_topic and not odometry_message:
                    continue
                if odometry_message and connection.msgtype != "nav_msgs/msg/Odometry":
                    assert odometry_accumulator is not None
                    odometry_accumulator.decode_errors += 1
                try:
                    message: Any = reader.deserialize(rawdata, connection.msgtype)
                    if specialized_topic:
                        specialized.add(connection.topic, message)
                    if odometry_message and connection.msgtype == "nav_msgs/msg/Odometry":
                        assert odometry_accumulator is not None
                        position = _vector(message.pose.pose.position)
                        linear = _vector(message.twist.twist.linear)
                        angular = _vector(message.twist.twist.angular)
                        rule = loaded_config.odometry if loaded_config is not None else None
                        odometry_accumulator.add(
                            int(timestamp_ns),
                            position,
                            linear,
                            angular,
                            max_speed_mps=rule.max_speed_mps if rule else None,
                            max_accel_mps2=rule.max_accel_mps2 if rule else None,
                            max_position_jump_m=rule.max_position_jump_m if rule else None,
                        )
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    if specialized_topic:
                        specialized.decode_failed(connection.topic)
                    if odometry_message:
                        assert odometry_accumulator is not None
                        odometry_accumulator.decode_errors += 1
                    warning_count = decode_warning_counts.get(connection.topic, 0)
                    if warning_count < 3:
                        warnings.append(
                            f"Could not decode specialized message on {connection.topic}: {exc}"
                        )
                    decode_warning_counts[connection.topic] = warning_count + 1

            topic_metrics = sorted(
                (
                    _finalize_topic(accumulator, start_time_ns, loaded_config)
                    for accumulator in accumulators.values()
                ),
                key=lambda item: item.name,
            )
            if not any(topic.message_count for topic in topic_metrics):
                warnings.append("Bag contains no messages.")
            odometry_metrics = None
            if odometry_accumulator is not None:
                odometry_messages = accumulators.get(odometry_accumulator.topic)
                odometry_metrics = _finalize_odometry(
                    odometry_accumulator,
                    odometry_messages.count if odometry_messages else 0,
                    start_time_ns,
                )
                if odometry_metrics.decode_errors:
                    warnings.append(
                        f"{odometry_metrics.decode_errors} odometry messages could not be decoded."
                    )

            status, checks = evaluate_gates(topic_metrics, odometry_metrics, loaded_config)
            subsystems, tf_topology, observed_rosout_nodes = specialized.finalize(odometry_metrics)
            framework = build_framework(subsystems, tf_topology, observed_rosout_nodes)
            ros_distro = getattr(reader, "ros_distro", None)
            if ros_distro is None and loaded_config is not None:
                ros_distro = loaded_config.ros_distro
            metadata = BagMetadata(
                source=str(bag_path),
                storage_format=_storage_format(bag_path),
                ros_distro=ros_distro,
                start_time_ns=start_time_ns,
                end_time_ns=end_time_ns,
                duration_s=_round((end_time_ns - start_time_ns) / 1e9) or 0.0,
                message_count=sum(item.message_count for item in topic_metrics),
                topic_count=len(topic_metrics),
            )
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(f"failed to analyze {bag_path}: {exc}") from exc

    return AnalysisResult(
        schema_version=SCHEMA_VERSION,
        tool_version=TOOL_VERSION,
        status=status,
        config_applied=loaded_config is not None,
        generated_at=datetime.now(timezone.utc).isoformat(),
        bag=metadata,
        topics=topic_metrics,
        checks=checks,
        odometry=odometry_metrics,
        subsystems=subsystems,
        framework=framework,
        warnings=warnings,
    )
