"""Serializable result models used by the API, CLI, and report renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["PASS", "WARN", "FAIL", "NOT_EVALUATED"]


@dataclass(slots=True)
class CheckResult:
    """One quality-gate evaluation."""

    check_id: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str
    topic: str | None = None
    metric: str | None = None
    measured: float | int | None = None
    threshold: float | int | None = None
    suggestion: str | None = None


@dataclass(slots=True)
class TopicMetrics:
    """Timing health metrics for one ROS topic."""

    name: str
    message_type: str
    message_count: int
    observed_duration_s: float
    mean_rate_hz: float | None
    median_rate_hz: float | None
    jitter_ms: float | None
    max_gap_ms: float | None
    gap_count: int
    gap_count_estimated: bool
    duplicate_timestamps: int
    reversed_timestamps: int
    sampled_points: int
    sample_limit: int
    timeline_s: list[float] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class OdometryMetrics:
    """Motion metrics derived from nav_msgs/msg/Odometry."""

    topic: str
    message_count: int
    decoded_count: int
    decode_errors: int
    total_distance_m: float | None
    displacement_m: float | None
    mean_linear_speed_mps: float | None
    max_linear_speed_mps: float | None
    p95_linear_speed_mps: float | None
    mean_angular_speed_rps: float | None
    max_angular_speed_rps: float | None
    p95_angular_speed_rps: float | None
    max_acceleration_mps2: float | None
    max_position_jump_m: float | None
    speed_violation_count: int
    acceleration_violation_count: int
    position_jump_count: int
    sampled_points: int
    sample_limit: int
    trajectory_x_m: list[float] = field(default_factory=list, repr=False)
    trajectory_y_m: list[float] = field(default_factory=list, repr=False)
    trajectory_time_s: list[float] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class BagMetadata:
    """Input bag metadata."""

    source: str
    storage_format: str
    ros_distro: str | None
    start_time_ns: int
    end_time_ns: int
    duration_s: float
    message_count: int
    topic_count: int


@dataclass(slots=True)
class AnalysisResult:
    """Stable public output of :func:`analyze_bag`."""

    schema_version: str
    tool_version: str
    status: Status
    config_applied: bool
    generated_at: str
    bag: BagMetadata
    topics: list[TopicMetrics]
    checks: list[CheckResult]
    odometry: OdometryMetrics | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self, *, include_samples: bool = False) -> dict[str, Any]:
        """Convert to a JSON-safe dictionary.

        Samples are excluded from the default machine-readable contract to keep
        ``summary.json`` compact. The report renderer can request them explicitly.
        """

        payload = asdict(self)
        if not include_samples:
            for topic in payload["topics"]:
                topic.pop("timeline_s", None)
            if payload["odometry"] is not None:
                payload["odometry"].pop("trajectory_x_m", None)
                payload["odometry"].pop("trajectory_y_m", None)
                payload["odometry"].pop("trajectory_time_s", None)
        return payload
