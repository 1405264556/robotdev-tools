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

    The bag contains standard lidar, IMU, odometry, TF, control, joint-state,
    localization, planning, and diagnostic streams. ``low_rate`` adds a visible
    scan dropout; ``jump`` adds localization and odometry discontinuities.
    """

    destination = Path(output)
    if destination.exists():
        raise FileExistsError(f"demo bag destination already exists: {destination}")
    if duration_s <= 1:
        raise ValueError("duration_s must be greater than 1")
    if scenario not in {"normal", "low_rate", "jump"}:
        raise ValueError(f"unknown demo scenario: {scenario}")

    typestore = get_typestore(Stores.LATEST)
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
    LaserScan = typestore.types["sensor_msgs/msg/LaserScan"]
    Imu = typestore.types["sensor_msgs/msg/Imu"]
    JointState = typestore.types["sensor_msgs/msg/JointState"]
    PoseStamped = typestore.types["geometry_msgs/msg/PoseStamped"]
    PoseWithCovarianceStamped = typestore.types["geometry_msgs/msg/PoseWithCovarianceStamped"]
    PathMessage = typestore.types["nav_msgs/msg/Path"]
    Transform = typestore.types["geometry_msgs/msg/Transform"]
    TransformStamped = typestore.types["geometry_msgs/msg/TransformStamped"]
    TFMessage = typestore.types["tf2_msgs/msg/TFMessage"]
    DiagnosticArray = typestore.types["diagnostic_msgs/msg/DiagnosticArray"]
    DiagnosticStatus = typestore.types["diagnostic_msgs/msg/DiagnosticStatus"]
    Log = typestore.types["rcl_interfaces/msg/Log"]

    plugin = StoragePlugin.MCAP if storage == "mcap" else StoragePlugin.SQLITE3
    start_ns = 1_700_000_000_000_000_000
    scan_period_ns = 100_000_000
    odom_period_ns = 50_000_000
    imu_period_ns = 50_000_000
    control_period_ns = 100_000_000
    localization_period_ns = 200_000_000
    plan_period_ns = 1_000_000_000
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
        events.append((start_ns + index * odom_period_ns, "tf", index))
        events.append((start_ns + index * odom_period_ns, "joints", index))
    imu_count = int(duration_s * 20)
    for index in range(imu_count):
        events.append((start_ns + index * imu_period_ns, "imu", index))
    control_count = int(duration_s * 10)
    for index in range(control_count):
        events.append((start_ns + index * control_period_ns, "control", index))
    localization_count = int(duration_s * 5)
    for index in range(localization_count):
        events.append((start_ns + index * localization_period_ns, "localization", index))
    plan_count = max(1, int(duration_s))
    for index in range(plan_count):
        events.append((start_ns + index * plan_period_ns, "plan", index))
        events.append((start_ns + index * plan_period_ns, "diagnostics", index))
    events.append((start_ns, "tf_static", 0))
    for index in range(9):
        events.append((start_ns + index, "rosout", index))
    events.sort(key=lambda item: (item[0], item[1]))

    with Writer(destination, version=9, storage_plugin=plugin) as writer:
        scan_connection = writer.add_connection("/scan", LaserScan.__msgtype__, typestore=typestore)
        odom_connection = writer.add_connection("/odom", Odometry.__msgtype__, typestore=typestore)
        imu_connection = writer.add_connection("/imu/data", Imu.__msgtype__, typestore=typestore)
        tf_connection = writer.add_connection("/tf", TFMessage.__msgtype__, typestore=typestore)
        tf_static_connection = writer.add_connection(
            "/tf_static", TFMessage.__msgtype__, typestore=typestore
        )
        control_connection = writer.add_connection(
            "/cmd_vel", Twist.__msgtype__, typestore=typestore
        )
        joint_connection = writer.add_connection(
            "/joint_states", JointState.__msgtype__, typestore=typestore
        )
        localization_connection = writer.add_connection(
            "/amcl_pose", PoseWithCovarianceStamped.__msgtype__, typestore=typestore
        )
        plan_connection = writer.add_connection(
            "/plan", PathMessage.__msgtype__, typestore=typestore
        )
        diagnostic_connection = writer.add_connection(
            "/diagnostics", DiagnosticArray.__msgtype__, typestore=typestore
        )
        rosout_connection = writer.add_connection("/rosout", Log.__msgtype__, typestore=typestore)
        covariance: Any = np.zeros(36, dtype=np.float64)

        def header(timestamp_ns: int, frame_id: str) -> Any:
            sec, nanosec = divmod(timestamp_ns, 1_000_000_000)
            return Header(
                stamp=Time(sec=int(sec), nanosec=int(nanosec)),
                frame_id=frame_id,
            )

        def pose_at(index: int, period_ns: int) -> tuple[float, float, float]:
            elapsed = index * period_ns / 1e9
            x = 0.4 * elapsed
            y = 0.25 * math.sin(elapsed)
            if scenario == "jump" and elapsed >= duration_s / 2:
                x += 2.0
            return elapsed, x, y

        for timestamp, kind, index in events:
            if kind == "scan":
                ranges = np.array(
                    [2.5 + 0.4 * math.sin(index * 0.03 + beam * 0.02) for beam in range(360)],
                    dtype=np.float32,
                )
                message = LaserScan(
                    header=header(timestamp, "laser"),
                    angle_min=-math.pi,
                    angle_max=math.pi,
                    angle_increment=2 * math.pi / 360,
                    time_increment=0.0,
                    scan_time=0.1,
                    range_min=0.1,
                    range_max=20.0,
                    ranges=ranges,
                    intensities=np.full(360, 100.0, dtype=np.float32),
                )
                writer.write(
                    scan_connection,
                    timestamp,
                    typestore.serialize_cdr(message, LaserScan.__msgtype__),
                )
                continue
            if kind == "odom":
                elapsed, x, y = pose_at(index, odom_period_ns)
                message = Odometry(
                    header=header(timestamp, "odom"),
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
            elif kind == "imu":
                message = Imu(
                    header=header(timestamp, "imu_link"),
                    orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                    orientation_covariance=np.eye(3, dtype=np.float64).reshape(9) * 0.01,
                    angular_velocity=Vector3(x=0.0, y=0.0, z=0.1),
                    angular_velocity_covariance=np.eye(3, dtype=np.float64).reshape(9) * 0.01,
                    linear_acceleration=Vector3(x=0.0, y=0.0, z=9.81),
                    linear_acceleration_covariance=np.eye(3, dtype=np.float64).reshape(9) * 0.04,
                )
                writer.write(
                    imu_connection,
                    timestamp,
                    typestore.serialize_cdr(message, Imu.__msgtype__),
                )
            elif kind == "control":
                elapsed = index * control_period_ns / 1e9
                message = Twist(
                    linear=Vector3(x=0.4 if elapsed < duration_s - 0.5 else 0.0, y=0.0, z=0.0),
                    angular=Vector3(x=0.0, y=0.0, z=0.1),
                )
                writer.write(
                    control_connection,
                    timestamp,
                    typestore.serialize_cdr(message, Twist.__msgtype__),
                )
            elif kind == "joints":
                elapsed = index * odom_period_ns / 1e9
                message = JointState(
                    header=header(timestamp, "base_link"),
                    name=["left_wheel_joint", "right_wheel_joint"],
                    position=np.array([elapsed * 4.0, elapsed * 4.1], dtype=np.float64),
                    velocity=np.array([4.0, 4.1], dtype=np.float64),
                    effort=np.array([], dtype=np.float64),
                )
                writer.write(
                    joint_connection,
                    timestamp,
                    typestore.serialize_cdr(message, JointState.__msgtype__),
                )
            elif kind == "localization":
                _, x, y = pose_at(index, localization_period_ns)
                message = PoseWithCovarianceStamped(
                    header=header(timestamp, "map"),
                    pose=PoseWithCovariance(
                        pose=Pose(
                            position=Point(x=x, y=y, z=0.0),
                            orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                        ),
                        covariance=covariance.copy(),
                    ),
                )
                writer.write(
                    localization_connection,
                    timestamp,
                    typestore.serialize_cdr(message, PoseWithCovarianceStamped.__msgtype__),
                )
            elif kind == "plan":
                poses = []
                for offset in range(6):
                    path_x = index * 0.4 + offset * 0.2
                    poses.append(
                        PoseStamped(
                            header=header(timestamp, "map"),
                            pose=Pose(
                                position=Point(x=path_x, y=0.2 * math.sin(path_x), z=0.0),
                                orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                            ),
                        )
                    )
                message = PathMessage(header=header(timestamp, "map"), poses=poses)
                writer.write(
                    plan_connection,
                    timestamp,
                    typestore.serialize_cdr(message, PathMessage.__msgtype__),
                )
            elif kind == "rosout":
                node_names = (
                    "lidar_driver",
                    "imu_driver",
                    "wheel_odometry",
                    "robot_state_publisher",
                    "base_controller",
                    "joint_state_broadcaster",
                    "localization",
                    "planner",
                    "diagnostic_aggregator",
                )
                message = Log(
                    stamp=header(timestamp, "").stamp,
                    level=20,
                    name=node_names[index],
                    msg="RobotDev demo node active",
                    file="demo.py",
                    function="generate_demo_bag",
                    line=1,
                )
                writer.write(
                    rosout_connection,
                    timestamp,
                    typestore.serialize_cdr(message, Log.__msgtype__),
                )
            elif kind == "diagnostics":
                level = 0
                diagnostic_text = "System nominal"
                if scenario == "low_rate" and index >= plan_count // 2:
                    level = 1
                    diagnostic_text = "Lidar update rate degraded"
                elif scenario == "jump" and index >= plan_count // 2:
                    level = 2
                    diagnostic_text = "Localization discontinuity detected"
                status = DiagnosticStatus(
                    level=level,
                    name="robotdev_demo",
                    message=diagnostic_text,
                    hardware_id="synthetic_robot",
                    values=[],
                )
                message = DiagnosticArray(header=header(timestamp, "base_link"), status=[status])
                writer.write(
                    diagnostic_connection,
                    timestamp,
                    typestore.serialize_cdr(message, DiagnosticArray.__msgtype__),
                )
            elif kind in {"tf", "tf_static"}:
                if kind == "tf_static":
                    transforms = [
                        TransformStamped(
                            header=header(timestamp, "base_link"),
                            child_frame_id="laser",
                            transform=Transform(
                                translation=Vector3(x=0.2, y=0.0, z=0.3),
                                rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                            ),
                        ),
                        TransformStamped(
                            header=header(timestamp, "base_link"),
                            child_frame_id="imu_link",
                            transform=Transform(
                                translation=Vector3(x=0.0, y=0.0, z=0.2),
                                rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                            ),
                        ),
                    ]
                    connection = tf_static_connection
                else:
                    _, x, y = pose_at(index, odom_period_ns)
                    transforms = [
                        TransformStamped(
                            header=header(timestamp, "map"),
                            child_frame_id="odom",
                            transform=Transform(
                                translation=Vector3(x=0.0, y=0.0, z=0.0),
                                rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                            ),
                        ),
                        TransformStamped(
                            header=header(timestamp, "odom"),
                            child_frame_id="base_link",
                            transform=Transform(
                                translation=Vector3(x=x, y=y, z=0.0),
                                rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                            ),
                        ),
                    ]
                    connection = tf_connection
                message = TFMessage(transforms=transforms)
                writer.write(
                    connection,
                    timestamp,
                    typestore.serialize_cdr(message, TFMessage.__msgtype__),
                )
    return destination
