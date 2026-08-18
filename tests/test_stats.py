import pytest

from robotdev_tools.stats import OnlineMoments, TopicAccumulator, percentile


def test_online_moments_are_exact() -> None:
    moments = OnlineMoments()
    for value in (1.0, 2.0, 3.0):
        moments.add(value)
    assert moments.mean == 2
    assert moments.maximum == 3
    assert moments.stddev == 1


def test_percentile_interpolates() -> None:
    assert percentile([], 0.5) is None
    assert percentile([1.0], 0.95) == 1
    assert percentile([0.0, 10.0], 0.5) == 5


def test_timing_counts_duplicate_reverse_and_gap() -> None:
    accumulator = TopicAccumulator("/scan", "std_msgs/msg/Float64", sample_limit=100)
    for timestamp in (0, 100_000_000, 100_000_000, 50_000_000, 500_000_000):
        accumulator.add(timestamp)
    assert accumulator.count == 5
    assert accumulator.duplicate_timestamps == 1
    assert accumulator.reversed_timestamps == 1
    gaps, estimated = accumulator.gap_summary(250)
    assert gaps == 1
    assert estimated is False


@pytest.mark.slow
def test_million_timestamps_remain_memory_bounded() -> None:
    accumulator = TopicAccumulator("/imu", "sensor_msgs/msg/Imu", sample_limit=20_000)
    for index in range(1_000_000):
        accumulator.add(index * 5_000_000)
    assert accumulator.count == 1_000_000
    assert len(accumulator.timeline.items) == 20_000
    assert len(accumulator.delta_sample.items) == 20_000
    assert accumulator.deltas_ms.mean == pytest.approx(5.0)
