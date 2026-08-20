# Changelog

All notable changes to RobotDev Tools are documented here.

## Unreleased

## 0.3.0 - 2026-08-20

- Improve GitHub discoverability with explicit rosbag2 analyzer, validator, diagnostics, MCAP/DB3,
  automated-testing, and quality-gate terminology in repository metadata and README entry points.
- Add fast recursive rosbag2 discovery for standard directories, raw DB3/MCAP files, metadata paths,
  split recordings, Unicode paths, and nested experiment folders.
- Add storage magic detection and lightweight previews for message count, duration, Topic names, and
  ROS message types without deserializing payloads.
- Add `robotdev discover PATH`, human-readable output, JSON output, and configurable scan depth.
- Redesign the desktop interface around a multi-bag candidate table, type preview, input validation,
  automatic report-path suggestions, and clearer bilingual workflow states.

## 0.2.0 - 2026-08-18

- Add a local desktop interface through `robotdev gui` with file/folder selection and automatic
  report opening.
- Expand Windows, Linux, PowerShell, CMD, Bash, server, installation, upgrade, and troubleshooting
  instructions.
- Add reproducible demo dataset and real-bag acceptance procedures.
- Add specialized analysis for LiDAR, IMU, odometry, TF, control commands, joint states,
  localization, planning paths, and diagnostic status messages.
- Add offline node-responsibility inference, configurable Topic-based node contracts, ROS data-flow
  visualization, and TF topology checks.
- Redesign the self-contained HTML report around experiment overview, ROS framework health,
  subsystem diagnostics, TF relations, quality gates, and timing/trajectory evidence.

## 0.1.0 - 2026-08-18

- Add ROS-free SQLite3 and MCAP analysis.
- Add bounded-memory topic timing and odometry metrics.
- Add versioned YAML quality gates with PASS/WARN/FAIL results and CI exit codes.
- Add self-contained HTML and compact JSON reports.
- Add deterministic normal, low-rate, and odometry-jump demo bags.
