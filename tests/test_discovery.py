import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robotdev_tools.cli import app
from robotdev_tools.demo import generate_demo_bag
from robotdev_tools.discovery import (
    MCAP_MAGIC,
    SQLITE_MAGIC,
    detect_storage_file,
    discover_rosbags,
    inspect_rosbag,
)

runner = CliRunner()


@pytest.mark.parametrize("storage", ["sqlite3", "mcap"])
def test_inspects_bag_directory_and_topic_types(tmp_path: Path, storage: str) -> None:
    bag = generate_demo_bag(tmp_path / f"bag-{storage}", storage=storage)  # type: ignore[arg-type]
    result = inspect_rosbag(bag)
    assert result.readable
    assert result.storage_format == storage
    assert result.input_kind == "standard_directory"
    assert result.metadata_present
    assert result.message_count == 545
    assert result.topic_count == 11
    assert result.duration_s == pytest.approx(4.95)
    assert ("/scan", "sensor_msgs/msg/LaserScan") in {
        (item.topic, item.message_type) for item in result.topic_types
    }
    assert result.to_dict()["path"] == str(bag.resolve())


@pytest.mark.parametrize(
    "storage,pattern,expected",
    [("sqlite3", "*.db3", "sqlite3"), ("mcap", "*.mcap", "mcap")],
)
def test_inspects_raw_storage_file(
    tmp_path: Path, storage: str, pattern: str, expected: str
) -> None:
    bag = generate_demo_bag(tmp_path / storage, storage=storage)  # type: ignore[arg-type]
    raw_file = next(bag.glob(pattern))
    result = inspect_rosbag(raw_file)
    assert result.readable
    assert result.input_kind == "raw_file"
    assert result.storage_format == expected
    assert len(result.storage_files) == 1


def test_recursively_discovers_multiple_bags_and_metadata_path(tmp_path: Path) -> None:
    first = generate_demo_bag(tmp_path / "实验 一" / "run")
    second = generate_demo_bag(tmp_path / "nested" / "level" / "run", storage="mcap")
    found = discover_rosbags(tmp_path, max_depth=3)
    assert [item.path for item in found] == sorted([first.resolve(), second.resolve()])
    assert {item.storage_format for item in found} == {"sqlite3", "mcap"}
    assert inspect_rosbag(first / "metadata.yaml").path == first.resolve()


def test_depth_limit_and_non_bag_paths(tmp_path: Path) -> None:
    generate_demo_bag(tmp_path / "one" / "two" / "bag")
    assert discover_rosbags(tmp_path, max_depth=1) == []
    assert discover_rosbags(tmp_path / "missing") == []
    with pytest.raises(ValueError, match="non-negative"):
        discover_rosbags(tmp_path, max_depth=-1)
    with pytest.raises(ValueError, match="positive"):
        discover_rosbags(tmp_path, max_candidates=0)


def test_corrupt_and_mixed_storage_are_identified_but_not_readable(tmp_path: Path) -> None:
    broken = tmp_path / "broken.db3"
    broken.write_bytes(b"not a sqlite database")
    assert detect_storage_file(broken) == "sqlite3"
    broken_result = inspect_rosbag(broken)
    assert not broken_result.readable
    assert broken_result.error is not None

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "a.db3").write_bytes(SQLITE_MAGIC)
    (mixed / "b.mcap").write_bytes(MCAP_MAGIC)
    mixed_result = inspect_rosbag(mixed)
    assert mixed_result.storage_format == "mixed"
    assert not mixed_result.readable
    assert "mixed" in (mixed_result.error or "").lower()


def test_cli_discover_text_and_json(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "bag")
    text_result = runner.invoke(app, ["discover", str(tmp_path)])
    assert text_result.exit_code == 0
    assert "Found 1 rosbag2 recording" in text_result.stdout
    assert "[sqlite3]" in text_result.stdout
    assert str(bag.resolve()) in text_result.stdout

    json_result = runner.invoke(app, ["discover", str(tmp_path), "--json"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload[0]["storage_format"] == "sqlite3"
    assert payload[0]["topic_count"] == 11
