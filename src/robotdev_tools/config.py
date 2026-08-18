"""Versioned YAML configuration for RobotDev quality gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a RobotDev configuration is invalid."""


@dataclass(slots=True)
class TopicRule:
    """Quality requirements for one topic."""

    required: bool = False
    expected_rate_hz: float | None = None
    rate_tolerance_pct: float = 10.0
    max_gap_ms: float | None = None
    max_jitter_ms: float | None = None


@dataclass(slots=True)
class OdometryRule:
    """Motion quality requirements."""

    topic: str = "/odom"
    max_speed_mps: float | None = None
    max_accel_mps2: float | None = None
    max_position_jump_m: float | None = None


@dataclass(slots=True)
class AnalysisConfig:
    """Top-level versioned configuration."""

    version: int = 1
    warn_margin_pct: float = 10.0
    topics: dict[str, TopicRule] = field(default_factory=dict)
    odometry: OdometryRule | None = None
    ros_distro: str | None = None


ConfigInput = AnalysisConfig | str | Path | Mapping[str, Any] | None


def _positive(name: str, value: Any, *, allow_zero: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    number = float(value)
    if number < 0 or (number == 0 and not allow_zero):
        comparator = "non-negative" if allow_zero else "positive"
        raise ConfigError(f"{name} must be {comparator}")
    return number


def _from_mapping(data: Mapping[str, Any]) -> AnalysisConfig:
    unknown = set(data) - {"version", "warn_margin_pct", "topics", "odometry", "ros_distro"}
    if unknown:
        raise ConfigError(f"unknown top-level keys: {', '.join(sorted(unknown))}")
    version = data.get("version", 1)
    if version != 1:
        raise ConfigError(f"unsupported config version: {version!r}; expected 1")
    warn_margin = _positive("warn_margin_pct", data.get("warn_margin_pct", 10), allow_zero=True)
    assert warn_margin is not None
    if warn_margin >= 100:
        raise ConfigError("warn_margin_pct must be below 100")

    topics_data = data.get("topics", {})
    if not isinstance(topics_data, Mapping):
        raise ConfigError("topics must be a mapping of topic names to rules")
    topics: dict[str, TopicRule] = {}
    allowed_topic = {
        "required",
        "expected_rate_hz",
        "rate_tolerance_pct",
        "max_gap_ms",
        "max_jitter_ms",
    }
    for topic, raw in topics_data.items():
        if not isinstance(topic, str) or not topic.startswith("/"):
            raise ConfigError(f"topic name must start with '/': {topic!r}")
        if not isinstance(raw, Mapping):
            raise ConfigError(f"rule for {topic} must be a mapping")
        extra = set(raw) - allowed_topic
        if extra:
            raise ConfigError(f"unknown keys for {topic}: {', '.join(sorted(extra))}")
        required = raw.get("required", False)
        if not isinstance(required, bool):
            raise ConfigError(f"topics.{topic}.required must be true or false")
        tolerance = _positive(
            f"topics.{topic}.rate_tolerance_pct",
            raw.get("rate_tolerance_pct", 10),
            allow_zero=True,
        )
        assert tolerance is not None
        if tolerance >= 100:
            raise ConfigError(f"topics.{topic}.rate_tolerance_pct must be below 100")
        topics[topic] = TopicRule(
            required=required,
            expected_rate_hz=_positive(
                f"topics.{topic}.expected_rate_hz", raw.get("expected_rate_hz")
            ),
            rate_tolerance_pct=tolerance,
            max_gap_ms=_positive(f"topics.{topic}.max_gap_ms", raw.get("max_gap_ms")),
            max_jitter_ms=_positive(
                f"topics.{topic}.max_jitter_ms", raw.get("max_jitter_ms")
            ),
        )

    odom_raw = data.get("odometry")
    odometry: OdometryRule | None = None
    if odom_raw is not None:
        if not isinstance(odom_raw, Mapping):
            raise ConfigError("odometry must be a mapping")
        allowed_odom = {
            "topic",
            "max_speed_mps",
            "max_accel_mps2",
            "max_position_jump_m",
        }
        extra = set(odom_raw) - allowed_odom
        if extra:
            raise ConfigError(f"unknown odometry keys: {', '.join(sorted(extra))}")
        topic = odom_raw.get("topic", "/odom")
        if not isinstance(topic, str) or not topic.startswith("/"):
            raise ConfigError("odometry.topic must start with '/'")
        odometry = OdometryRule(
            topic=topic,
            max_speed_mps=_positive("odometry.max_speed_mps", odom_raw.get("max_speed_mps")),
            max_accel_mps2=_positive(
                "odometry.max_accel_mps2", odom_raw.get("max_accel_mps2")
            ),
            max_position_jump_m=_positive(
                "odometry.max_position_jump_m", odom_raw.get("max_position_jump_m")
            ),
        )

    ros_distro = data.get("ros_distro")
    if ros_distro is not None and not isinstance(ros_distro, str):
        raise ConfigError("ros_distro must be a string")
    return AnalysisConfig(
        version=1,
        warn_margin_pct=warn_margin,
        topics=topics,
        odometry=odometry,
        ros_distro=ros_distro,
    )


def load_config(config: ConfigInput) -> AnalysisConfig | None:
    """Load an :class:`AnalysisConfig` from YAML, mapping, or an existing object."""

    if config is None:
        return None
    if isinstance(config, AnalysisConfig):
        return config
    if isinstance(config, (str, Path)):
        path = Path(config)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ConfigError("config root must be a mapping")
        return _from_mapping(raw)
    if isinstance(config, Mapping):
        return _from_mapping(config)
    raise ConfigError(f"unsupported config input: {type(config).__name__}")
