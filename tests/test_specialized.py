from types import SimpleNamespace

from robotdev_tools.specialized import (
    DIAGNOSTICS,
    IMU,
    JOINT_STATE,
    PATH,
    POINT_CLOUD,
    TF_MESSAGE,
    DiagnosticAccumulator,
    ImuAccumulator,
    JointAccumulator,
    PathAccumulator,
    PointCloudAccumulator,
    TFAccumulator,
    _tf_subsystem,
    _tf_topology,
)


def ns(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


def vector(x: float, y: float, z: float) -> SimpleNamespace:
    return ns(x=x, y=y, z=z)


def test_empty_point_cloud_is_degraded() -> None:
    accumulator = PointCloudAccumulator("/points", POINT_CLOUD)
    accumulator.add(ns(width=0, height=1, is_dense=True, header=ns(frame_id="lidar")))
    result = accumulator.finalize()
    assert result.status == "DEGRADED"
    assert any(metric.key == "empty" and metric.value == 1 for metric in result.metrics)


def test_nonfinite_imu_is_fault() -> None:
    accumulator = ImuAccumulator("/imu", IMU)
    accumulator.add(
        ns(
            angular_velocity=vector(float("nan"), 0, 0),
            linear_acceleration=vector(0, 0, 9.81),
            orientation=ns(x=0.0, y=0.0, z=0.0, w=1.0),
            orientation_covariance=[0.0] * 9,
        )
    )
    assert accumulator.finalize().status == "FAULT"


def test_joint_array_mismatch_is_degraded() -> None:
    accumulator = JointAccumulator("/joint_states", JOINT_STATE)
    accumulator.add(ns(name=["left", "right"], position=[1.0], velocity=[], effort=[]))
    result = accumulator.finalize()
    assert result.status == "DEGRADED"
    assert "do not match" in result.issues[0]


def test_empty_planning_path_is_degraded() -> None:
    accumulator = PathAccumulator("/plan", PATH)
    accumulator.add(ns(poses=[], header=ns(frame_id="map")))
    assert accumulator.finalize().status == "DEGRADED"


def test_diagnostic_error_is_fault() -> None:
    accumulator = DiagnosticAccumulator("/diagnostics", DIAGNOSTICS)
    accumulator.add(ns(status=[ns(level=2, name="motor", message="over temperature")]))
    result = accumulator.finalize()
    assert result.status == "FAULT"
    assert result.issues == ["motor: ERROR: over temperature"]


def test_tf_cycle_and_multiple_parent_are_reported() -> None:
    accumulator = TFAccumulator("/tf", TF_MESSAGE)
    accumulator.edge_counts = {
        ("map", "odom", False): 1,
        ("odom", "base", False): 1,
        ("base", "map", False): 1,
        ("alternate", "base", False): 1,
    }
    accumulator.decoded_count = 1
    topology = _tf_topology([accumulator])
    result = _tf_subsystem([accumulator], topology)
    assert result.status == "FAULT"
    assert topology.cycles
    assert topology.multiple_parent_frames == ["base"]
