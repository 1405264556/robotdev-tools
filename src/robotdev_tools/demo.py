"""Deterministic synthetic rosbag2 fixtures for demos and tests."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import numpy as np
from rosbags.rosbag2 import StoragePlugin, Writer
from rosbags.typesys import Stores, get_typestore

Scenario = Literal["normal", "low_rate", "jump"]
Storage = Literal["sqlite3", "mcap"]


def generate_demo_bag(
    output: str | Path,
    *,
    scenario: Scenario = "normal",
    storage: Storage = "sqlite3",
    duration_s: float = 5.0,
) -> Path:
    """Generate a small deterministic ROS 2 bag.

    The bag contains ``/scan`` timing samples and ``/odom`` standard odometry.
    ``low_rate`` adds a visible scan dropout; ``jump`` adds a localization jump.
    """

    destination = Path(output)
    if destination.exists():
        raise FileExistsError(f"demo bag destination already exists: {destination}")
    if duration_s <= 1:
        raise ValueError("duration_s must be greater than 1")
    if scenario not in {"normal", "low_rate", "jump"}:
        raise ValueError(f"unknown demo scenario: {scenario}")

    typestore = get_typestore(Stores.LATEST)
    Float64 = typestore.types["std_msgs/msg/Float64"]
    Time = typestore.types["builtin_interfaces/msg/Time"]
    Header = typestore.types["std_msgs/msg/Header"]
    Point = typestore.types["geometry_msgs/msg/Point"]
    Quaternion = typestore.types["geometry_msgs/msg/Quaternion"]
    Pose = typestore.types["geometry_msgs/msg/Pose"]
    PoseWithCovariance = typestore.types["geometry_msgs/msg/PoseWithCovariance"]
    Vector3 = typestore.types["geometry_msgs/msg/Vector3"]
    Twist = typestore.types["geometry_msgs/msg/Twist"]
    TwistWithCovariance = typestore.types["geometry_msgs/msg/TwistWithCovariance"]
    Odometry = typestore.types["nav_msgs/msg/Odometry"]

    plugin = StoragePlugin.MCAP if storage == "mcap" else StoragePlugin.SQLITE3
    start_ns = 1_700_000_000_000_000_000
    scan_period_ns = 100_000_000
    odom_period_ns = 50_000_000
    events: list[tuple[int, str, int]] = []
    scan_count = int(duration_s * 10)
    for index in range(scan_count):
        if scenario == "low_rate":
            if index % 2:
                continue
            timestamp = start_ns + index * scan_period_ns
            if index >= scan_count // 2:
                timestamp += 450_000_000
        else:
            timestamp = start_ns + index * scan_period_ns
        events.append((timestamp, "scan", index))
    odom_count = int(duration_s * 20)
    for index in range(odom_count):
        events.append((start_ns + index * odom_period_ns, "odom", index))
    events.sort(key=lambda item: (item[0], item[1]))

    with Writer(destination, version=9, storage_plugin=plugin) as writer:
        scan_connection = writer.add_connection(
            "/scan", Float64.__msgtype__, typestore=typestore
        )
        odom_connection = writer.add_connection(
            "/odom", Odometry.__msgtype__, typestore=typestore
        )
        covariance: Any = np.zeros(36, dtype=np.float64)
        for timestamp, kind, index in events:
            if kind == "scan":
                message = Float64(data=float(index))
                writer.write(
                    scan_connection,
                    timestamp,
                    typestore.serialize_cdr(message, Float64.__msgtype__),
                )
                continue
            elapsed = index * odom_period_ns / 1e9
            x = 0.4 * elapsed
            y = 0.25 * math.sin(elapsed)
            if scenario == "jump" and index >= odom_count // 2:
                x += 2.0
            sec, nanosec = divmod(timestamp, 1_000_000_000)
            message = Odometry(
                header=Header(stamp=Time(sec=int(sec), nanosec=int(nanosec)), frame_id="odom"),
                child_frame_id="base_link",
                pose=PoseWithCovariance(
                    pose=Pose(
                        position=Point(x=x, y=y, z=0.0),
                        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                    ),
                    covariance=covariance.copy(),
                ),
                twist=TwistWithCovariance(
                    twist=Twist(
                        linear=Vector3(x=0.4, y=0.25 * math.cos(elapsed), z=0.0),
                        angular=Vector3(x=0.0, y=0.0, z=0.1),
                    ),
                    covariance=covariance.copy(),
                ),
            )
            writer.write(
                odom_connection,
                timestamp,
                typestore.serialize_cdr(message, Odometry.__msgtype__),
            )
    return destination
