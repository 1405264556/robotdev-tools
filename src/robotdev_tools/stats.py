"""Memory-bounded streaming statistics."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


class Reservoir(Generic[T]):
    """Deterministic fixed-size reservoir sample."""

    def __init__(self, limit: int, *, seed: str) -> None:
        self.limit = limit
        self.seen = 0
        self.items: list[T] = []
        self._random = random.Random(seed)

    def add(self, item: T) -> None:
        self.seen += 1
        if len(self.items) < self.limit:
            self.items.append(item)
            return
        index = self._random.randrange(self.seen)
        if index < self.limit:
            self.items[index] = item


@dataclass(slots=True)
class OnlineMoments:
    """Exact online mean and sample standard deviation."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    maximum: float | None = None
    total: float = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        if self.maximum is None or value > self.maximum:
            self.maximum = value

    @property
    def stddev(self) -> float | None:
        if self.count < 2:
            return None
        return math.sqrt(self.m2 / (self.count - 1))


def percentile(values: list[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile from a sample."""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(slots=True)
class TopicAccumulator:
    """Streaming timing state for one topic."""

    name: str
    message_type: str
    sample_limit: int
    count: int = 0
    minimum_ns: int | None = None
    maximum_ns: int | None = None
    previous_ns: int | None = None
    duplicate_timestamps: int = 0
    reversed_timestamps: int = 0
    deltas_ms: OnlineMoments = field(default_factory=OnlineMoments)
    timeline: Reservoir[int] = field(init=False)
    delta_sample: Reservoir[float] = field(init=False)

    def __post_init__(self) -> None:
        self.timeline = Reservoir(self.sample_limit, seed=f"timeline:{self.name}")
        self.delta_sample = Reservoir(self.sample_limit, seed=f"delta:{self.name}")

    def add(self, timestamp_ns: int) -> None:
        self.count += 1
        self.timeline.add(timestamp_ns)
        if self.minimum_ns is None or timestamp_ns < self.minimum_ns:
            self.minimum_ns = timestamp_ns
        if self.maximum_ns is None or timestamp_ns > self.maximum_ns:
            self.maximum_ns = timestamp_ns
        if self.previous_ns is not None:
            delta_ns = timestamp_ns - self.previous_ns
            if delta_ns == 0:
                self.duplicate_timestamps += 1
            elif delta_ns < 0:
                self.reversed_timestamps += 1
            else:
                delta_ms = delta_ns / 1_000_000
                self.deltas_ms.add(delta_ms)
                self.delta_sample.add(delta_ms)
        self.previous_ns = timestamp_ns

    def gap_summary(self, threshold_ms: float | None = None) -> tuple[int, bool]:
        sample = self.delta_sample.items
        if not sample:
            return 0, False
        if threshold_ms is None:
            median = percentile(sample, 0.5)
            if median is None:
                return 0, False
            threshold_ms = median * 3
        sampled_gaps = sum(delta > threshold_ms for delta in sample)
        if self.delta_sample.seen <= self.sample_limit:
            return sampled_gaps, False
        estimated = round(sampled_gaps / len(sample) * self.delta_sample.seen)
        return estimated, True


@dataclass(slots=True)
class OdometryAccumulator:
    """Memory-bounded odometry aggregation."""

    topic: str
    sample_limit: int
    decoded_count: int = 0
    decode_errors: int = 0
    total_distance_m: float = 0.0
    first_position: tuple[float, float, float] | None = None
    last_position: tuple[float, float, float] | None = None
    previous_timestamp_ns: int | None = None
    previous_speed_mps: float | None = None
    linear_speeds: OnlineMoments = field(default_factory=OnlineMoments)
    angular_speeds: OnlineMoments = field(default_factory=OnlineMoments)
    accelerations: OnlineMoments = field(default_factory=OnlineMoments)
    position_jumps: OnlineMoments = field(default_factory=OnlineMoments)
    speed_violation_count: int = 0
    acceleration_violation_count: int = 0
    position_jump_count: int = 0
    trajectory: Reservoir[tuple[int, float, float]] = field(init=False)
    linear_sample: Reservoir[float] = field(init=False)
    angular_sample: Reservoir[float] = field(init=False)

    def __post_init__(self) -> None:
        self.trajectory = Reservoir(self.sample_limit, seed=f"odom-path:{self.topic}")
        self.linear_sample = Reservoir(self.sample_limit, seed=f"odom-linear:{self.topic}")
        self.angular_sample = Reservoir(self.sample_limit, seed=f"odom-angular:{self.topic}")

    def add(
        self,
        timestamp_ns: int,
        position: tuple[float, float, float],
        linear_velocity: tuple[float, float, float],
        angular_velocity: tuple[float, float, float],
        *,
        max_speed_mps: float | None,
        max_accel_mps2: float | None,
        max_position_jump_m: float | None,
    ) -> None:
        self.decoded_count += 1
        x, y, _ = position
        self.trajectory.add((timestamp_ns, x, y))
        if self.first_position is None:
            self.first_position = position
        if self.last_position is not None:
            jump = math.dist(position, self.last_position)
            self.total_distance_m += jump
            self.position_jumps.add(jump)
            if max_position_jump_m is not None and jump > max_position_jump_m:
                self.position_jump_count += 1
        self.last_position = position

        linear_speed = math.sqrt(sum(component * component for component in linear_velocity))
        angular_speed = math.sqrt(sum(component * component for component in angular_velocity))
        self.linear_speeds.add(linear_speed)
        self.angular_speeds.add(angular_speed)
        self.linear_sample.add(linear_speed)
        self.angular_sample.add(angular_speed)
        if max_speed_mps is not None and linear_speed > max_speed_mps:
            self.speed_violation_count += 1

        if self.previous_timestamp_ns is not None and self.previous_speed_mps is not None:
            delta_s = (timestamp_ns - self.previous_timestamp_ns) / 1_000_000_000
            if delta_s > 0:
                acceleration = abs(linear_speed - self.previous_speed_mps) / delta_s
                self.accelerations.add(acceleration)
                if max_accel_mps2 is not None and acceleration > max_accel_mps2:
                    self.acceleration_violation_count += 1
        self.previous_timestamp_ns = timestamp_ns
        self.previous_speed_mps = linear_speed
