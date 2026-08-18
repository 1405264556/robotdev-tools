from pathlib import Path

import pytest
from rosbags.rosbag2 import Writer
from rosbags.typesys import Stores, get_typestore

from robotdev_tools.analyzer import AnalysisError, analyze_bag
from robotdev_tools.demo import generate_demo_bag


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parents[1] / "examples" / "robotdev.yaml"


@pytest.mark.parametrize("storage", ["sqlite3", "mcap"])
def test_normal_bag_passes(tmp_path: Path, config_path: Path, storage: str) -> None:
    bag = generate_demo_bag(tmp_path / f"normal-{storage}", storage=storage)  # type: ignore[arg-type]
    result = analyze_bag(bag, config_path)
    assert result.status == "PASS"
    assert result.bag.message_count == 150
    assert result.bag.topic_count == 2
    assert {topic.name for topic in result.topics} == {"/scan", "/odom"}
    assert result.odometry is not None
    assert result.odometry.decoded_count == 100
    assert result.odometry.total_distance_m is not None
    assert result.odometry.total_distance_m > 2


@pytest.mark.parametrize(
    "scenario,failed_check",
    [
        ("low_rate", "topic:/scan:rate"),
        ("jump", "odometry:/odom:position_jump"),
    ],
)
def test_fault_bags_fail(
    tmp_path: Path, config_path: Path, scenario: str, failed_check: str
) -> None:
    bag = generate_demo_bag(tmp_path / scenario, scenario=scenario)  # type: ignore[arg-type]
    result = analyze_bag(bag, config_path)
    assert result.status == "FAIL"
    assert failed_check in {check.check_id for check in result.checks if check.status == "FAIL"}


def test_without_config_is_not_evaluated(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "normal")
    result = analyze_bag(bag)
    assert result.status == "NOT_EVALUATED"
    assert result.checks == []
    assert result.odometry is not None


@pytest.mark.parametrize("storage,pattern", [("sqlite3", "*.db3"), ("mcap", "*.mcap")])
def test_raw_storage_file_input(
    tmp_path: Path, config_path: Path, storage: str, pattern: str
) -> None:
    bag = generate_demo_bag(tmp_path / f"bag-{storage}", storage=storage)  # type: ignore[arg-type]
    raw_file = next(bag.glob(pattern))
    result = analyze_bag(raw_file, config_path)
    assert result.status == "PASS"
    assert result.bag.storage_format == storage


def test_unicode_and_spaces_in_path(tmp_path: Path, config_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "机器人 实验")
    assert analyze_bag(bag, config_path).status == "PASS"


def test_missing_path_is_clear(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="does not exist"):
        analyze_bag(tmp_path / "missing")


def test_small_sample_limit_is_rejected(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "normal")
    with pytest.raises(AnalysisError, match="at least 10"):
        analyze_bag(bag, sample_limit=2)


def test_empty_topic_is_reported_without_negative_duration(tmp_path: Path) -> None:
    typestore = get_typestore(Stores.LATEST)
    message_type = typestore.types["std_msgs/msg/Float64"]
    bag = tmp_path / "empty"
    with Writer(bag, version=9) as writer:
        writer.add_connection("/empty", message_type.__msgtype__, typestore=typestore)
    result = analyze_bag(bag)
    assert result.status == "NOT_EVALUATED"
    assert result.bag.duration_s == 0
    assert result.topics[0].message_count == 0
    assert "Bag contains no messages." in result.warnings


def test_non_odometry_topic_degrades_to_timing_metrics(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "normal")
    result = analyze_bag(
        bag,
        {
            "version": 1,
            "odometry": {"topic": "/scan", "max_position_jump_m": 0.5},
        },
    )
    assert result.status == "FAIL"
    assert next(topic for topic in result.topics if topic.name == "/scan").message_count == 50
    assert result.odometry is not None
    assert result.odometry.decoded_count == 0
    assert result.odometry.decode_errors == 50
