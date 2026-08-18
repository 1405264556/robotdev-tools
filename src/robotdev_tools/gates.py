"""Quality-gate evaluation."""

from __future__ import annotations

from typing import Literal

from robotdev_tools.config import AnalysisConfig
from robotdev_tools.models import CheckResult, OdometryMetrics, Status, TopicMetrics

GateStatus = Literal["PASS", "WARN", "FAIL"]


def _upper_status(value: float, limit: float, warn_margin_pct: float) -> GateStatus:
    if value > limit:
        return "FAIL"
    if value >= limit * (1 - warn_margin_pct / 100):
        return "WARN"
    return "PASS"


def _lower_status(value: float, limit: float, warn_margin_pct: float) -> GateStatus:
    if value < limit:
        return "FAIL"
    if value <= limit * (1 + warn_margin_pct / 100):
        return "WARN"
    return "PASS"


def evaluate_gates(
    topics: list[TopicMetrics],
    odometry: OdometryMetrics | None,
    config: AnalysisConfig | None,
) -> tuple[Status, list[CheckResult]]:
    """Evaluate configured gates and return overall status plus details."""

    if config is None:
        return "NOT_EVALUATED", []
    checks: list[CheckResult] = []
    by_name = {topic.name: topic for topic in topics}
    for name, topic_rule in config.topics.items():
        metrics = by_name.get(name)
        if metrics is None:
            status: GateStatus = "FAIL" if topic_rule.required else "WARN"
            checks.append(
                CheckResult(
                    check_id=f"topic:{name}:present",
                    status=status,
                    topic=name,
                    metric="present",
                    measured=0,
                    threshold=1,
                    message=f"Topic {name} is missing.",
                    suggestion="Confirm the recorder topic list and publisher lifecycle.",
                )
            )
            continue
        checks.append(
            CheckResult(
                check_id=f"topic:{name}:present",
                status="PASS",
                topic=name,
                metric="present",
                measured=1,
                threshold=1,
                message=f"Topic {name} is present.",
            )
        )
        if topic_rule.expected_rate_hz is not None and metrics.mean_rate_hz is not None:
            minimum = topic_rule.expected_rate_hz * (1 - topic_rule.rate_tolerance_pct / 100)
            status = _lower_status(metrics.mean_rate_hz, minimum, config.warn_margin_pct)
            checks.append(
                CheckResult(
                    check_id=f"topic:{name}:rate",
                    status=status,
                    topic=name,
                    metric="mean_rate_hz",
                    measured=metrics.mean_rate_hz,
                    threshold=minimum,
                    message=(
                        f"Mean rate is {metrics.mean_rate_hz:.3f} Hz; minimum is {minimum:.3f} Hz."
                    ),
                    suggestion="Inspect publisher load, QoS, transport, and recording throughput."
                    if status != "PASS"
                    else None,
                )
            )
        for key, measured, limit, suggestion in (
            (
                "max_gap",
                metrics.max_gap_ms,
                topic_rule.max_gap_ms,
                "Check sensor stalls, executor starvation, and recorder disk throughput.",
            ),
            (
                "jitter",
                metrics.jitter_ms,
                topic_rule.max_jitter_ms,
                "Check scheduling load, callback contention, and timestamp source stability.",
            ),
        ):
            if measured is None or limit is None:
                continue
            status = _upper_status(measured, limit, config.warn_margin_pct)
            checks.append(
                CheckResult(
                    check_id=f"topic:{name}:{key}",
                    status=status,
                    topic=name,
                    metric=f"{key}_ms",
                    measured=measured,
                    threshold=limit,
                    message=(
                        f"{key.replace('_', ' ').title()} is {measured:.3f} ms; "
                        f"limit is {limit:.3f} ms."
                    ),
                    suggestion=suggestion if status != "PASS" else None,
                )
            )

    for node_name, node_rule in config.nodes.items():
        recorded_topics = [topic for topic in node_rule.topics if topic in by_name]
        missing_topics = [topic for topic in node_rule.topics if topic not in by_name]
        if missing_topics:
            status = "FAIL" if node_rule.required else "WARN"
            checks.append(
                CheckResult(
                    check_id=f"node:{node_name}:topic_contract",
                    status=status,
                    topic=missing_topics[0],
                    metric="recorded_topics",
                    measured=len(recorded_topics),
                    threshold=len(node_rule.topics),
                    message=(
                        f"Node responsibility {node_name} is missing recorded evidence: "
                        f"{', '.join(missing_topics)}."
                    ),
                    suggestion=(
                        "Check the node lifecycle and recorder Topic list. Rosbag2 cannot prove "
                        "the runtime process name, so this gate validates its Topic contract."
                    ),
                )
            )
        else:
            checks.append(
                CheckResult(
                    check_id=f"node:{node_name}:topic_contract",
                    status="PASS",
                    metric="recorded_topics",
                    measured=len(recorded_topics),
                    threshold=len(node_rule.topics),
                    message=(f"Node responsibility {node_name} has all configured Topic evidence."),
                    suggestion=(
                        "The actual runtime node name is not stored in rosbag2; use ros2 node info "
                        "for live publisher/subscriber verification."
                    ),
                )
            )

    if config.odometry is not None:
        odometry_rule = config.odometry
        if odometry is None or odometry.topic != odometry_rule.topic or odometry.decoded_count == 0:
            checks.append(
                CheckResult(
                    check_id=f"odometry:{odometry_rule.topic}:decoded",
                    status="FAIL",
                    topic=odometry_rule.topic,
                    metric="decoded_count",
                    measured=0,
                    threshold=1,
                    message=f"Odometry topic {odometry_rule.topic} could not be decoded.",
                    suggestion=(
                        "Record nav_msgs/msg/Odometry with embedded message definitions "
                        "or choose the correct topic."
                    ),
                )
            )
        else:
            checks.append(
                CheckResult(
                    check_id=f"odometry:{odometry_rule.topic}:decoded",
                    status="PASS",
                    topic=odometry_rule.topic,
                    metric="decoded_count",
                    measured=odometry.decoded_count,
                    threshold=1,
                    message=f"Decoded {odometry.decoded_count} odometry messages.",
                )
            )
            for key, measured, limit, suggestion in (
                (
                    "speed",
                    odometry.max_linear_speed_mps,
                    odometry_rule.max_speed_mps,
                    "Check controller limits, odometry scaling, and encoder calibration.",
                ),
                (
                    "acceleration",
                    odometry.max_acceleration_mps2,
                    odometry_rule.max_accel_mps2,
                    "Inspect abrupt velocity commands and timestamp discontinuities.",
                ),
                (
                    "position_jump",
                    odometry.max_position_jump_m,
                    odometry_rule.max_position_jump_m,
                    "Inspect localization resets, frame changes, and odometry discontinuities.",
                ),
            ):
                if measured is None or limit is None:
                    continue
                status = _upper_status(measured, limit, config.warn_margin_pct)
                checks.append(
                    CheckResult(
                        check_id=f"odometry:{odometry_rule.topic}:{key}",
                        status=status,
                        topic=odometry_rule.topic,
                        metric=key,
                        measured=measured,
                        threshold=limit,
                        message=(
                            f"Maximum {key.replace('_', ' ')} is {measured:.3f}; "
                            f"limit is {limit:.3f}."
                        ),
                        suggestion=suggestion if status != "PASS" else None,
                    )
                )

    statuses = {check.status for check in checks}
    if "FAIL" in statuses:
        return "FAIL", checks
    if "WARN" in statuses:
        return "WARN", checks
    return "PASS", checks
