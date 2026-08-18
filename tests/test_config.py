from pathlib import Path

import pytest

from robotdev_tools.config import ConfigError, load_config


def test_loads_versioned_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "robotdev.yaml"
    config_path.write_text(
        "version: 1\nwarn_margin_pct: 5\ntopics:\n  /scan:\n    required: true\n"
        "    expected_rate_hz: 10\nnodes:\n  lidar_driver:\n    required: true\n"
        "    topics: [/scan]\nodometry:\n  topic: /odom\n  max_speed_mps: 2\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config is not None
    assert config.warn_margin_pct == 5
    assert config.topics["/scan"].expected_rate_hz == 10
    assert config.nodes["lidar_driver"].topics == ["/scan"]
    assert config.odometry is not None
    assert config.odometry.max_speed_mps == 2


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"version": 2}, "unsupported config version"),
        ({"version": 1, "surprise": True}, "unknown top-level"),
        ({"version": 1, "topics": {"scan": {}}}, "must start with"),
        ({"version": 1, "warn_margin_pct": 100}, "below 100"),
        ({"version": 1, "topics": {"/scan": {"expected_rate_hz": -1}}}, "positive"),
        ({"version": 1, "nodes": {"lidar": {"topics": []}}}, "non-empty list"),
        ({"version": 1, "nodes": {"lidar": {"topics": ["scan"]}}}, "start with"),
    ],
)
def test_rejects_invalid_config(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(payload)


def test_none_means_no_gates() -> None:
    assert load_config(None) is None
