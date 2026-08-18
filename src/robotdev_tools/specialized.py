"""Streaming ROS subsystem analysis and offline framework reconstruction."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from robotdev_tools.models import (
    DataFlowEdge,
    DetailMetric,
    FrameEdge,
    HealthStatus,
    InferredNode,
    OdometryMetrics,
    ROSFrameworkAnalysis,
    SubsystemAnalysis,
)
from robotdev_tools.stats import OnlineMoments

LASER_SCAN = "sensor_msgs/msg/LaserScan"
POINT_CLOUD = "sensor_msgs/msg/PointCloud2"
IMU = "sensor_msgs/msg/Imu"
TWIST = "geometry_msgs/msg/Twist"
TWIST_STAMPED = "geometry_msgs/msg/TwistStamped"
JOINT_STATE = "sensor_msgs/msg/JointState"
POSE_COV = "geometry_msgs/msg/PoseWithCovarianceStamped"
POSE_STAMPED = "geometry_msgs/msg/PoseStamped"
PATH = "nav_msgs/msg/Path"
DIAGNOSTICS = "diagnostic_msgs/msg/DiagnosticArray"
TF_MESSAGE = "tf2_msgs/msg/TFMessage"
ROSOUT_LOG = "rcl_interfaces/msg/Log"

SUPPORTED_TYPES = {
    LASER_SCAN,
    POINT_CLOUD,
    IMU,
    TWIST,
    TWIST_STAMPED,
    JOINT_STATE,
    POSE_COV,
    POSE_STAMPED,
    PATH,
    DIAGNOSTICS,
    TF_MESSAGE,
    ROSOUT_LOG,
}


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _norm(vector: Any) -> float:
    return math.sqrt(float(vector.x) ** 2 + float(vector.y) ** 2 + float(vector.z) ** 2)


def _quaternion_norm(quaternion: Any) -> float:
    return math.sqrt(
        float(quaternion.x) ** 2
        + float(quaternion.y) ** 2
        + float(quaternion.z) ** 2
        + float(quaternion.w) ** 2
    )


def _finite_sequence(values: Any) -> bool:
    return all(math.isfinite(float(value)) for value in values)


@dataclass(slots=True)
class BaseAccumulator:
    topic: str
    message_type: str
    decoded_count: int = 0
    decode_errors: int = 0

    def decode_failed(self) -> None:
        self.decode_errors += 1


@dataclass(slots=True)
class RosoutAccumulator(BaseAccumulator):
    """Collect node names explicitly self-reported through ROS 2 logging."""

    node_names: set[str] = field(default_factory=set)

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        name = str(message.name).strip()
        if name:
            self.node_names.add(name)


@dataclass(slots=True)
class LaserAccumulator(BaseAccumulator):
    beam_count: int = 0
    valid_beams: int = 0
    nan_beams: int = 0
    infinite_beams: int = 0
    out_of_range_beams: int = 0
    minimum_scan_size: int | None = None
    maximum_scan_size: int = 0

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        ranges = message.ranges
        size = len(ranges)
        self.beam_count += size
        self.minimum_scan_size = (
            size if self.minimum_scan_size is None else min(self.minimum_scan_size, size)
        )
        self.maximum_scan_size = max(self.maximum_scan_size, size)
        minimum = float(message.range_min)
        maximum = float(message.range_max)
        for raw in ranges:
            value = float(raw)
            if math.isnan(value):
                self.nan_beams += 1
            elif math.isinf(value):
                self.infinite_beams += 1
            elif value < minimum or value > maximum:
                self.out_of_range_beams += 1
            else:
                self.valid_beams += 1

    def finalize(self) -> SubsystemAnalysis:
        ratio = self.valid_beams / self.beam_count * 100 if self.beam_count else 0.0
        inconsistent = self.minimum_scan_size != self.maximum_scan_size
        issues: list[str] = []
        suggestions: list[str] = []
        status: HealthStatus = "HEALTHY"
        if ratio < 50:
            status = "FAULT"
            issues.append(f"Only {ratio:.1f}% of laser ranges are valid.")
        elif ratio < 90:
            status = "DEGRADED"
            issues.append(f"Laser valid-range ratio is {ratio:.1f}%.")
        if inconsistent:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append("Laser scan size changes during the recording.")
        if self.decode_errors:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append(f"{self.decode_errors} laser messages could not be decoded.")
        if issues:
            suggestions.append(
                "Check range limits, reflective/transparent surfaces, driver configuration, "
                "and sensor power."
            )
        return SubsystemAnalysis(
            subsystem_id=f"lidar:{self.topic}",
            name=f"Laser radar / 激光雷达 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded scans", self.decoded_count),
                DetailMetric("beams", "Total beams", self.beam_count),
                DetailMetric("valid_ratio", "Valid ranges", _round(ratio), "%"),
                DetailMetric("nan", "NaN ranges", self.nan_beams),
                DetailMetric("inf", "Infinite ranges", self.infinite_beams),
                DetailMetric("out_of_range", "Out-of-range", self.out_of_range_beams),
                DetailMetric("scan_size_min", "Minimum scan size", self.minimum_scan_size),
                DetailMetric("scan_size_max", "Maximum scan size", self.maximum_scan_size),
            ],
            issues=issues,
            suggestions=suggestions,
        )


@dataclass(slots=True)
class PointCloudAccumulator(BaseAccumulator):
    point_count: int = 0
    empty_clouds: int = 0
    non_dense_clouds: int = 0
    frame_ids: set[str] = field(default_factory=set)

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        points = int(message.width) * int(message.height)
        self.point_count += points
        if points == 0:
            self.empty_clouds += 1
        if not bool(message.is_dense):
            self.non_dense_clouds += 1
        frame_id = str(message.header.frame_id)
        if frame_id:
            self.frame_ids.add(frame_id)

    def finalize(self) -> SubsystemAnalysis:
        issues: list[str] = []
        status: HealthStatus = "HEALTHY"
        if self.empty_clouds:
            status = "DEGRADED"
            issues.append(f"{self.empty_clouds} point clouds are empty.")
        if self.decode_errors:
            status = "DEGRADED"
            issues.append(f"{self.decode_errors} point clouds could not be decoded.")
        mean_points = self.point_count / self.decoded_count if self.decoded_count else 0.0
        return SubsystemAnalysis(
            subsystem_id=f"lidar:{self.topic}",
            name=f"Point-cloud lidar / 点云雷达 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded clouds", self.decoded_count),
                DetailMetric("mean_points", "Mean points/cloud", _round(mean_points)),
                DetailMetric("empty", "Empty clouds", self.empty_clouds),
                DetailMetric("non_dense", "Non-dense clouds", self.non_dense_clouds),
                DetailMetric("frames", "Frames", ", ".join(sorted(self.frame_ids)) or "—"),
            ],
            issues=issues,
            suggestions=["Check lidar packet loss and point-cloud conversion settings."]
            if issues
            else [],
        )


@dataclass(slots=True)
class ImuAccumulator(BaseAccumulator):
    angular_speed: OnlineMoments = field(default_factory=OnlineMoments)
    acceleration: OnlineMoments = field(default_factory=OnlineMoments)
    quaternion_error: OnlineMoments = field(default_factory=OnlineMoments)
    invalid_quaternions: int = 0
    nonfinite_messages: int = 0
    orientation_unavailable: int = 0

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        values = (
            message.angular_velocity.x,
            message.angular_velocity.y,
            message.angular_velocity.z,
            message.linear_acceleration.x,
            message.linear_acceleration.y,
            message.linear_acceleration.z,
            message.orientation.x,
            message.orientation.y,
            message.orientation.z,
            message.orientation.w,
        )
        if not _finite_sequence(values):
            self.nonfinite_messages += 1
            return
        self.angular_speed.add(_norm(message.angular_velocity))
        self.acceleration.add(_norm(message.linear_acceleration))
        quaternion_error = abs(_quaternion_norm(message.orientation) - 1.0)
        self.quaternion_error.add(quaternion_error)
        if quaternion_error > 0.1:
            self.invalid_quaternions += 1
        covariance = message.orientation_covariance
        if len(covariance) and float(covariance[0]) < 0:
            self.orientation_unavailable += 1

    def finalize(self) -> SubsystemAnalysis:
        issues: list[str] = []
        status: HealthStatus = "HEALTHY"
        if self.nonfinite_messages:
            status = "FAULT"
            issues.append(f"{self.nonfinite_messages} IMU messages contain NaN/Inf values.")
        if self.invalid_quaternions:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append(f"{self.invalid_quaternions} IMU orientations are not normalized.")
        if self.decode_errors:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append(f"{self.decode_errors} IMU messages could not be decoded.")
        return SubsystemAnalysis(
            subsystem_id=f"imu:{self.topic}",
            name=f"IMU / 惯性测量 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded messages", self.decoded_count),
                DetailMetric(
                    "max_angular", "Max angular speed", _round(self.angular_speed.maximum), "rad/s"
                ),
                DetailMetric(
                    "mean_accel",
                    "Mean acceleration norm",
                    _round(self.acceleration.mean if self.acceleration.count else None),
                    "m/s²",
                ),
                DetailMetric(
                    "max_accel", "Max acceleration norm", _round(self.acceleration.maximum), "m/s²"
                ),
                DetailMetric(
                    "quaternion_error",
                    "Max quaternion norm error",
                    _round(self.quaternion_error.maximum),
                ),
                DetailMetric(
                    "orientation_unavailable",
                    "Orientation unavailable",
                    self.orientation_unavailable,
                ),
                DetailMetric("nonfinite", "NaN/Inf messages", self.nonfinite_messages),
            ],
            issues=issues,
            suggestions=["Check IMU calibration, mounting, covariance flags, and driver scaling."]
            if issues
            else [],
        )


@dataclass(slots=True)
class ControlAccumulator(BaseAccumulator):
    linear_speed: OnlineMoments = field(default_factory=OnlineMoments)
    angular_speed: OnlineMoments = field(default_factory=OnlineMoments)
    zero_commands: int = 0
    nonfinite_messages: int = 0

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        twist = message.twist if self.message_type == TWIST_STAMPED else message
        values = (
            twist.linear.x,
            twist.linear.y,
            twist.linear.z,
            twist.angular.x,
            twist.angular.y,
            twist.angular.z,
        )
        if not _finite_sequence(values):
            self.nonfinite_messages += 1
            return
        linear = _norm(twist.linear)
        angular = _norm(twist.angular)
        self.linear_speed.add(linear)
        self.angular_speed.add(angular)
        if linear < 1e-6 and angular < 1e-6:
            self.zero_commands += 1

    def finalize(self) -> SubsystemAnalysis:
        status: HealthStatus = "FAULT" if self.nonfinite_messages else "HEALTHY"
        issues = (
            [f"{self.nonfinite_messages} control commands contain NaN/Inf values."]
            if self.nonfinite_messages
            else []
        )
        active_ratio = (
            (self.decoded_count - self.zero_commands) / self.decoded_count * 100
            if self.decoded_count
            else 0.0
        )
        return SubsystemAnalysis(
            subsystem_id=f"control:{self.topic}",
            name=f"Control command / 控制指令 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded commands", self.decoded_count),
                DetailMetric("active_ratio", "Active commands", _round(active_ratio), "%"),
                DetailMetric(
                    "max_linear", "Max linear command", _round(self.linear_speed.maximum), "m/s"
                ),
                DetailMetric(
                    "max_angular",
                    "Max angular command",
                    _round(self.angular_speed.maximum),
                    "rad/s",
                ),
                DetailMetric("zero", "Zero commands", self.zero_commands),
                DetailMetric("nonfinite", "NaN/Inf commands", self.nonfinite_messages),
            ],
            issues=issues,
            suggestions=["Stop the controller and inspect command arbitration immediately."]
            if issues
            else [],
        )


@dataclass(slots=True)
class JointAccumulator(BaseAccumulator):
    joint_names: set[str] = field(default_factory=set)
    previous_joint_set: frozenset[str] | None = None
    joint_set_changes: int = 0
    array_mismatches: int = 0
    duplicate_names: int = 0
    nonfinite_values: int = 0

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        names = [str(name) for name in message.name]
        name_set = frozenset(names)
        if len(name_set) != len(names):
            self.duplicate_names += 1
        if self.previous_joint_set is not None and name_set != self.previous_joint_set:
            self.joint_set_changes += 1
        self.previous_joint_set = name_set
        self.joint_names.update(name_set)
        for values in (message.position, message.velocity, message.effort):
            if len(values) not in {0, len(names)}:
                self.array_mismatches += 1
            self.nonfinite_values += sum(not math.isfinite(float(value)) for value in values)

    def finalize(self) -> SubsystemAnalysis:
        issues: list[str] = []
        status: HealthStatus = "HEALTHY"
        if self.nonfinite_values:
            status = "FAULT"
            issues.append(f"Joint states contain {self.nonfinite_values} NaN/Inf values.")
        if self.array_mismatches or self.duplicate_names or self.joint_set_changes:
            status = "DEGRADED" if status == "HEALTHY" else status
        if self.array_mismatches:
            issues.append(f"{self.array_mismatches} joint arrays do not match the name array.")
        if self.duplicate_names:
            issues.append(f"{self.duplicate_names} messages contain duplicate joint names.")
        if self.joint_set_changes:
            issues.append(f"The recorded joint set changes {self.joint_set_changes} times.")
        return SubsystemAnalysis(
            subsystem_id=f"joint_states:{self.topic}",
            name=f"Joint states / 关节状态 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded messages", self.decoded_count),
                DetailMetric("joints", "Observed joints", len(self.joint_names)),
                DetailMetric(
                    "joint_names", "Joint names", ", ".join(sorted(self.joint_names)) or "—"
                ),
                DetailMetric("set_changes", "Joint-set changes", self.joint_set_changes),
                DetailMetric("array_mismatch", "Array mismatches", self.array_mismatches),
                DetailMetric("nonfinite", "NaN/Inf values", self.nonfinite_values),
            ],
            issues=issues,
            suggestions=["Check joint_state publisher field lengths and controller lifecycle."]
            if issues
            else [],
        )


@dataclass(slots=True)
class LocalizationAccumulator(BaseAccumulator):
    previous_position: tuple[float, float, float] | None = None
    position_jumps: OnlineMoments = field(default_factory=OnlineMoments)
    covariance_xy: OnlineMoments = field(default_factory=OnlineMoments)
    nonfinite_messages: int = 0
    frame_ids: set[str] = field(default_factory=set)

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        pose_container = message.pose
        pose = pose_container.pose if hasattr(pose_container, "pose") else pose_container
        position = (float(pose.position.x), float(pose.position.y), float(pose.position.z))
        orientation = pose.orientation
        values = (*position, orientation.x, orientation.y, orientation.z, orientation.w)
        if not _finite_sequence(values):
            self.nonfinite_messages += 1
            return
        if self.previous_position is not None:
            self.position_jumps.add(math.dist(position, self.previous_position))
        self.previous_position = position
        frame_id = str(message.header.frame_id)
        if frame_id:
            self.frame_ids.add(frame_id)
        covariance = getattr(pose_container, "covariance", None)
        if covariance is not None and len(covariance) >= 8:
            xy = max(abs(float(covariance[0])), abs(float(covariance[7])))
            if math.isfinite(xy):
                self.covariance_xy.add(xy)

    def finalize(self) -> SubsystemAnalysis:
        maximum_jump = self.position_jumps.maximum
        issues: list[str] = []
        status: HealthStatus = "HEALTHY"
        if self.nonfinite_messages:
            status = "FAULT"
            issues.append(f"{self.nonfinite_messages} localization poses contain NaN/Inf values.")
        if maximum_jump is not None and maximum_jump > 1.0:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append(f"Localization position jumps by up to {maximum_jump:.3f} m.")
        if self.decode_errors:
            status = "DEGRADED" if status == "HEALTHY" else status
            issues.append(f"{self.decode_errors} localization messages could not be decoded.")
        return SubsystemAnalysis(
            subsystem_id=f"localization:{self.topic}",
            name=f"Localization / 定位结果 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Decoded poses", self.decoded_count),
                DetailMetric("max_jump", "Maximum position jump", _round(maximum_jump), "m"),
                DetailMetric(
                    "mean_covariance",
                    "Mean XY covariance",
                    _round(self.covariance_xy.mean if self.covariance_xy.count else None),
                ),
                DetailMetric(
                    "max_covariance", "Maximum XY covariance", _round(self.covariance_xy.maximum)
                ),
                DetailMetric(
                    "frames", "Reference frames", ", ".join(sorted(self.frame_ids)) or "—"
                ),
                DetailMetric("nonfinite", "NaN/Inf poses", self.nonfinite_messages),
            ],
            issues=issues,
            suggestions=[
                "Inspect localization resets, map/odom TF continuity, and covariance tuning."
            ]
            if issues
            else [],
        )


@dataclass(slots=True)
class PathAccumulator(BaseAccumulator):
    total_poses: int = 0
    empty_paths: int = 0
    maximum_poses: int = 0
    latest_path_length_m: float | None = None
    maximum_path_length_m: float = 0.0
    frame_ids: set[str] = field(default_factory=set)

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        poses = message.poses
        count = len(poses)
        self.total_poses += count
        self.maximum_poses = max(self.maximum_poses, count)
        if count == 0:
            self.empty_paths += 1
        length = 0.0
        previous: tuple[float, float, float] | None = None
        for stamped in poses:
            current = (
                float(stamped.pose.position.x),
                float(stamped.pose.position.y),
                float(stamped.pose.position.z),
            )
            if previous is not None:
                length += math.dist(previous, current)
            previous = current
        self.latest_path_length_m = length
        self.maximum_path_length_m = max(self.maximum_path_length_m, length)
        frame_id = str(message.header.frame_id)
        if frame_id:
            self.frame_ids.add(frame_id)

    def finalize(self) -> SubsystemAnalysis:
        status: HealthStatus = "DEGRADED" if self.empty_paths else "HEALTHY"
        issues = (
            [f"{self.empty_paths} planning messages contain an empty path."]
            if self.empty_paths
            else []
        )
        mean_poses = self.total_poses / self.decoded_count if self.decoded_count else 0.0
        return SubsystemAnalysis(
            subsystem_id=f"planning:{self.topic}",
            name=f"Planned path / 规划轨迹 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("decoded", "Plans", self.decoded_count),
                DetailMetric("empty", "Empty plans", self.empty_paths),
                DetailMetric("mean_poses", "Mean poses/plan", _round(mean_poses)),
                DetailMetric("max_poses", "Maximum poses", self.maximum_poses),
                DetailMetric(
                    "latest_length", "Latest path length", _round(self.latest_path_length_m), "m"
                ),
                DetailMetric(
                    "max_length", "Maximum path length", _round(self.maximum_path_length_m), "m"
                ),
                DetailMetric("frames", "Planning frames", ", ".join(sorted(self.frame_ids)) or "—"),
            ],
            issues=issues,
            suggestions=[
                "Inspect planner validity checks, costmap availability, and goal reachability."
            ]
            if issues
            else [],
        )


@dataclass(slots=True)
class DiagnosticAccumulator(BaseAccumulator):
    status_entries: int = 0
    ok_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    stale_count: int = 0
    affected_names: set[str] = field(default_factory=set)
    latest_faults: dict[str, str] = field(default_factory=dict)

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        for item in message.status:
            self.status_entries += 1
            level = int(item.level)
            name = str(item.name) or "unnamed diagnostic"
            text = str(item.message)
            if level == 0:
                self.ok_count += 1
                self.latest_faults.pop(name, None)
            elif level == 1:
                self.warning_count += 1
                self.affected_names.add(name)
                self.latest_faults[name] = f"WARN: {text}"
            elif level == 2:
                self.error_count += 1
                self.affected_names.add(name)
                self.latest_faults[name] = f"ERROR: {text}"
            else:
                self.stale_count += 1
                self.affected_names.add(name)
                self.latest_faults[name] = f"STALE: {text}"

    def finalize(self) -> SubsystemAnalysis:
        status: HealthStatus = "HEALTHY"
        if self.error_count:
            status = "FAULT"
        elif self.warning_count or self.stale_count:
            status = "DEGRADED"
        issues = [f"{name}: {message}" for name, message in sorted(self.latest_faults.items())]
        return SubsystemAnalysis(
            subsystem_id=f"diagnostics:{self.topic}",
            name=f"Diagnostics / 故障状态 · {self.topic}",
            status=status,
            topics=[self.topic],
            message_types=[self.message_type],
            metrics=[
                DetailMetric("messages", "Diagnostic arrays", self.decoded_count),
                DetailMetric("entries", "Status entries", self.status_entries),
                DetailMetric("ok", "OK", self.ok_count),
                DetailMetric("warn", "WARN", self.warning_count),
                DetailMetric("error", "ERROR", self.error_count),
                DetailMetric("stale", "STALE", self.stale_count),
                DetailMetric("affected", "Affected components", len(self.affected_names)),
            ],
            issues=issues,
            suggestions=[
                "Inspect the named hardware/software components and their diagnostic key-values."
            ]
            if issues
            else [],
        )


@dataclass(slots=True)
class TFAccumulator(BaseAccumulator):
    edge_counts: dict[tuple[str, str, bool], int] = field(default_factory=dict)
    invalid_quaternions: int = 0
    empty_frame_ids: int = 0

    def add(self, message: Any) -> None:
        self.decoded_count += 1
        is_static = self.topic.endswith("tf_static")
        for transform in message.transforms:
            parent = str(transform.header.frame_id).strip().lstrip("/")
            child = str(transform.child_frame_id).strip().lstrip("/")
            if not parent or not child:
                self.empty_frame_ids += 1
                continue
            key = (parent, child, is_static)
            self.edge_counts[key] = self.edge_counts.get(key, 0) + 1
            if abs(_quaternion_norm(transform.transform.rotation) - 1.0) > 0.1:
                self.invalid_quaternions += 1


@dataclass(slots=True)
class TFTopology:
    frame_edges: list[FrameEdge]
    roots: list[str]
    component_count: int
    cycles: list[list[str]]
    multiple_parent_frames: list[str]
    self_transforms: int
    invalid_quaternions: int
    empty_frame_ids: int


def _tf_topology(accumulators: list[TFAccumulator]) -> TFTopology:
    combined: dict[tuple[str, str, bool], int] = defaultdict(int)
    invalid_quaternions = 0
    empty_frame_ids = 0
    for accumulator in accumulators:
        invalid_quaternions += accumulator.invalid_quaternions
        empty_frame_ids += accumulator.empty_frame_ids
        for key, count in accumulator.edge_counts.items():
            combined[key] += count
    frame_edges = [
        FrameEdge(parent, child, count, is_static)
        for (parent, child, is_static), count in sorted(combined.items())
    ]
    adjacency: dict[str, set[str]] = defaultdict(set)
    undirected: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    self_transforms = 0
    for edge in frame_edges:
        nodes.update((edge.parent, edge.child))
        if edge.parent == edge.child:
            self_transforms += 1
        adjacency[edge.parent].add(edge.child)
        undirected[edge.parent].add(edge.child)
        undirected[edge.child].add(edge.parent)
        parents[edge.child].add(edge.parent)

    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if len(cycles) >= 20:
            return
        if node in visiting:
            start = visiting.index(node)
            cycle = [*visiting[start:], node]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.append(node)
        for child in adjacency[node]:
            visit(child)
        visiting.pop()
        visited.add(node)

    for frame in sorted(nodes):
        visit(frame)

    components = 0
    remaining = set(nodes)
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            current = stack.pop()
            neighbors = undirected[current] & remaining
            remaining.difference_update(neighbors)
            stack.extend(neighbors)

    roots = sorted(nodes - set(parents))
    multiple_parent_frames = sorted(child for child, values in parents.items() if len(values) > 1)
    return TFTopology(
        frame_edges=frame_edges,
        roots=roots,
        component_count=components,
        cycles=cycles,
        multiple_parent_frames=multiple_parent_frames,
        self_transforms=self_transforms,
        invalid_quaternions=invalid_quaternions,
        empty_frame_ids=empty_frame_ids,
    )


def _tf_subsystem(accumulators: list[TFAccumulator], topology: TFTopology) -> SubsystemAnalysis:
    topics = sorted({item.topic for item in accumulators})
    decoded = sum(item.decoded_count for item in accumulators)
    issues: list[str] = []
    status: HealthStatus = "HEALTHY"
    if topology.cycles or topology.self_transforms:
        status = "FAULT"
    elif (
        topology.multiple_parent_frames
        or topology.invalid_quaternions
        or topology.component_count > 1
    ):
        status = "DEGRADED"
    if topology.cycles:
        issues.append(f"TF graph contains {len(topology.cycles)} cycle(s).")
    if topology.self_transforms:
        issues.append(f"TF graph contains {topology.self_transforms} self-transform(s).")
    if topology.multiple_parent_frames:
        issues.append("Frames with multiple parents: " + ", ".join(topology.multiple_parent_frames))
    if topology.component_count > 1:
        issues.append(f"TF graph has {topology.component_count} disconnected components.")
    if topology.invalid_quaternions:
        issues.append(f"{topology.invalid_quaternions} TF rotations are not normalized.")
    if topology.empty_frame_ids:
        issues.append(f"{topology.empty_frame_ids} transforms have an empty frame ID.")
    return SubsystemAnalysis(
        subsystem_id="tf:framework",
        name="TF frame system / TF 坐标系",
        status=status,
        topics=topics,
        message_types=[TF_MESSAGE],
        metrics=[
            DetailMetric("messages", "TF messages", decoded),
            DetailMetric(
                "frames",
                "Frames",
                len(
                    {value for edge in topology.frame_edges for value in (edge.parent, edge.child)}
                ),
            ),
            DetailMetric("edges", "Frame relations", len(topology.frame_edges)),
            DetailMetric("roots", "Root frames", ", ".join(topology.roots) or "—"),
            DetailMetric("components", "Connected components", topology.component_count),
            DetailMetric("cycles", "Cycles", len(topology.cycles)),
            DetailMetric(
                "multiple_parents", "Multiple-parent frames", len(topology.multiple_parent_frames)
            ),
        ],
        issues=issues,
        suggestions=[
            "Ensure TF forms one acyclic tree and each child frame has one authoritative parent."
        ]
        if issues
        else [],
    )


def odometry_subsystem(odometry: OdometryMetrics) -> SubsystemAnalysis:
    issues: list[str] = []
    status: HealthStatus = "HEALTHY"
    if odometry.decoded_count == 0:
        status = "FAULT"
        issues.append("No odometry messages could be decoded.")
    elif odometry.decode_errors:
        status = "DEGRADED"
        issues.append(f"{odometry.decode_errors} odometry messages could not be decoded.")
    if odometry.position_jump_count or (
        odometry.max_position_jump_m is not None and odometry.max_position_jump_m > 1.0
    ):
        status = "FAULT" if odometry.position_jump_count else "DEGRADED"
        issues.append(f"Odometry position jumps by up to {odometry.max_position_jump_m:.3f} m.")
    if odometry.speed_violation_count or odometry.acceleration_violation_count:
        status = "FAULT"
        issues.append(
            f"Configured motion limits were exceeded: speed={odometry.speed_violation_count}, "
            f"acceleration={odometry.acceleration_violation_count}."
        )
    return SubsystemAnalysis(
        subsystem_id=f"odometry:{odometry.topic}",
        name=f"Odometry / 里程计 · {odometry.topic}",
        status=status,
        topics=[odometry.topic],
        message_types=["nav_msgs/msg/Odometry"],
        metrics=[
            DetailMetric("decoded", "Decoded messages", odometry.decoded_count),
            DetailMetric("distance", "Total distance", odometry.total_distance_m, "m"),
            DetailMetric("displacement", "Displacement", odometry.displacement_m, "m"),
            DetailMetric("max_speed", "Maximum speed", odometry.max_linear_speed_mps, "m/s"),
            DetailMetric("p95_speed", "P95 speed", odometry.p95_linear_speed_mps, "m/s"),
            DetailMetric(
                "max_acceleration", "Maximum acceleration", odometry.max_acceleration_mps2, "m/s²"
            ),
            DetailMetric("max_jump", "Maximum position jump", odometry.max_position_jump_m, "m"),
        ],
        issues=issues,
        suggestions=[
            "Inspect encoder scaling, localization resets, timestamps, and controller limits."
        ]
        if issues
        else [],
    )


class SpecializedAnalyzers:
    """Own per-topic streaming decoders for supported standard ROS messages."""

    def __init__(self) -> None:
        self.accumulators: dict[str, BaseAccumulator] = {}

    @staticmethod
    def recognizes(message_type: str) -> bool:
        return message_type in SUPPORTED_TYPES

    def prepare(self, topic: str, message_type: str) -> None:
        if topic in self.accumulators or message_type not in SUPPORTED_TYPES:
            return
        accumulator_types: dict[str, type[BaseAccumulator]] = {
            LASER_SCAN: LaserAccumulator,
            POINT_CLOUD: PointCloudAccumulator,
            IMU: ImuAccumulator,
            TWIST: ControlAccumulator,
            TWIST_STAMPED: ControlAccumulator,
            JOINT_STATE: JointAccumulator,
            POSE_COV: LocalizationAccumulator,
            POSE_STAMPED: LocalizationAccumulator,
            PATH: PathAccumulator,
            DIAGNOSTICS: DiagnosticAccumulator,
            TF_MESSAGE: TFAccumulator,
            ROSOUT_LOG: RosoutAccumulator,
        }
        self.accumulators[topic] = accumulator_types[message_type](topic, message_type)

    def add(self, topic: str, message: Any) -> None:
        accumulator = self.accumulators[topic]
        add = getattr(accumulator, "add")  # noqa: B009 - heterogeneous accumulators
        add(message)

    def decode_failed(self, topic: str) -> None:
        self.accumulators[topic].decode_failed()

    def finalize(
        self, odometry: OdometryMetrics | None
    ) -> tuple[list[SubsystemAnalysis], TFTopology, list[str]]:
        subsystems: list[SubsystemAnalysis] = []
        tf_accumulators: list[TFAccumulator] = []
        observed_rosout_nodes: set[str] = set()
        for accumulator in self.accumulators.values():
            if isinstance(accumulator, TFAccumulator):
                tf_accumulators.append(accumulator)
                continue
            if isinstance(accumulator, RosoutAccumulator):
                observed_rosout_nodes.update(accumulator.node_names)
                continue
            finalize = getattr(accumulator, "finalize")  # noqa: B009
            subsystems.append(finalize())
        topology = _tf_topology(tf_accumulators)
        if tf_accumulators:
            subsystems.append(_tf_subsystem(tf_accumulators, topology))
        if odometry is not None:
            subsystems.append(odometry_subsystem(odometry))
        return (
            sorted(subsystems, key=lambda item: item.subsystem_id),
            topology,
            sorted(observed_rosout_nodes),
        )


ROLE_INFO: dict[str, tuple[str, str]] = {
    "lidar": ("Lidar source / 激光雷达节点", "Publishes range or point-cloud observations"),
    "imu": ("IMU source / IMU 节点", "Publishes inertial orientation and motion"),
    "odometry": ("Odometry source / 里程计节点", "Publishes local motion estimates"),
    "tf": ("TF broadcaster / TF 发布节点", "Maintains coordinate-frame relations"),
    "joint_states": ("Joint-state source / 关节状态节点", "Publishes robot joint feedback"),
    "localization": ("Localization / 定位节点", "Publishes global or map-relative pose estimates"),
    "planning": ("Planner / 规划节点", "Publishes planned paths"),
    "control": ("Controller / 控制节点", "Publishes robot motion commands"),
    "diagnostics": ("Diagnostics / 故障诊断节点", "Publishes component health and faults"),
}


def build_framework(
    subsystems: list[SubsystemAnalysis],
    topology: TFTopology,
    observed_rosout_nodes: list[str] | None = None,
) -> ROSFrameworkAnalysis:
    """Build an explicitly inferred ROS responsibility graph."""

    inferred_nodes: list[InferredNode] = []
    by_role: dict[str, list[InferredNode]] = defaultdict(list)
    for subsystem in subsystems:
        role = subsystem.subsystem_id.split(":", 1)[0]
        display_name, responsibility = ROLE_INFO[role]
        node = InferredNode(
            node_id=subsystem.subsystem_id,
            display_name=display_name,
            responsibility=responsibility,
            status=subsystem.status,
            topics=subsystem.topics,
            evidence=(
                "Inferred from recorded standard message types; actual runtime node name "
                "is not stored in rosbag2."
            ),
            confidence="HIGH",
        )
        inferred_nodes.append(node)
        by_role[role].append(node)

    def first(role: str) -> InferredNode | None:
        values = by_role.get(role)
        return values[0] if values else None

    flows: list[DataFlowEdge] = []

    def connect(source_role: str, target_role: str, relation: str) -> None:
        source = first(source_role)
        target = first(target_role)
        if source is not None and target is not None:
            flows.append(DataFlowEdge(source.node_id, target.node_id, relation))

    connect("lidar", "localization", "range observations")
    connect("imu", "localization", "inertial observations")
    connect("odometry", "localization", "local motion prior")
    connect("joint_states", "tf", "robot kinematic state")
    connect("tf", "localization", "frame transforms")
    connect("localization", "planning", "estimated robot pose")
    connect("planning", "control", "planned trajectory")
    connect("control", "odometry", "commanded motion feedback loop")
    connect("control", "joint_states", "actuation feedback loop")
    if first("localization") is None:
        connect("odometry", "planning", "local pose estimate")

    core_roles = list(ROLE_INFO)
    observed_roles = set(by_role)
    missing_roles = [ROLE_INFO[role][0] for role in core_roles if role not in observed_roles]
    coverage = len(observed_roles) / len(core_roles) * 100
    statuses = {subsystem.status for subsystem in subsystems}
    framework_status: HealthStatus
    if "FAULT" in statuses:
        framework_status = "FAULT"
    elif "DEGRADED" in statuses:
        framework_status = "DEGRADED"
    elif subsystems:
        framework_status = "HEALTHY"
    else:
        framework_status = "NO_DATA"
    return ROSFrameworkAnalysis(
        discovery_mode="INFERRED_FROM_BAG",
        status=framework_status,
        coverage_pct=round(coverage, 1),
        observed_rosout_nodes=observed_rosout_nodes or [],
        inferred_nodes=sorted(inferred_nodes, key=lambda item: item.node_id),
        data_flows=flows,
        frame_edges=topology.frame_edges,
        tf_roots=topology.roots,
        tf_component_count=topology.component_count,
        tf_cycles=topology.cycles,
        multiple_parent_frames=topology.multiple_parent_frames,
        missing_subsystems=missing_roles,
        limitations=[
            "Rosbag2 records messages and Topic types, but normally does not record live "
            "node names, publishers, subscribers, services, actions, parameters, or "
            "lifecycle states.",
            "Nodes shown here are responsibility-level inferences from recorded evidence, "
            "not a replacement for ros2 node/info or a live graph monitor.",
            "Names observed in /rosout are self-reported logging identities; they do not expose "
            "publisher/subscriber edges or prove that a node was alive for the full recording.",
        ],
    )
