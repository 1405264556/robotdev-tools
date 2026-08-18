# RobotDev Tools — ROSBag2 Automated Analyzer & Validator

**ROS 2 rosbag2 自动化检测、质量验收与故障诊断工具 / Automated ROS 2 bag analysis,
validation, diagnostics, and PASS/FAIL reporting.**

[![CI](https://github.com/1405264556/robotdev-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/1405264556/robotdev-tools/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/1405264556/robotdev-tools)](https://github.com/1405264556/robotdev-tools/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10--3.13-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/github/license/1405264556/robotdev-tools)](LICENSE)

> Search terms / 检索关键词：`rosbag2 analyzer` · `rosbag2 validator` ·
> `ROS 2 bag diagnostics` · `MCAP analyzer` · `DB3 analyzer` · `rosbag2 quality gate` ·
> `rosbag2 自动化检测` · `ROS2 bag 故障诊断`

[中文](#中文) · [English](#english) · [详细使用指南](docs/USAGE.zh-CN.md) ·
[测试数据与验收](docs/TESTING.md)

![RobotDev Tools report preview](docs/images/report-preview.png)

## 中文

RobotDev Tools 是面向机器人实验室的 **ROS 2 rosbag2 自动化检测、分析与实验验收工具**。
它也可以作为 rosbag2 analyzer、rosbag2 validator、ROS bag diagnostics 或 CI quality gate
使用。工具直接读取
rosbag2（SQLite3 / MCAP），自动计算 Topic 健康度，并对激光雷达、IMU、里程计、TF、
控制指令、关节状态、定位、规划轨迹和故障诊断进行专项检测。新版报告还会根据 bag 中的
Topic/类型证据重建 ROS 节点职责和数据流，生成 PASS / WARN / FAIL 门禁、自包含 HTML
可视化报告以及适合 CI 的 JSON 结果。

- 不需要安装 ROS 2。
- 数据只在本机处理，不上传 bag。
- Windows 和 Linux 均支持 Python 3.10–3.13。
- 可使用终端批处理，也可使用本地桌面界面选择文件。

### 一条命令完成 rosbag2 自动检测

```bash
robotdev analyze /path/to/rosbag2 --config robotdev.yaml --output report
```

输出独立的 `report.html` 和适合自动化/CI 的 `summary.json`；故障门禁返回退出码 `2`。

### 应该选择哪种使用方式？

| 使用方式 | 适合场景 | 启动方法 | 结果查看 |
|---|---|---|---|
| 桌面界面 | 首次体验、单次分析、不熟悉命令行 | `robotdev gui` | 完成后自动在浏览器打开 |
| 终端命令 | 批量实验、脚本、服务器、CI | `robotdev analyze ...` | 手动打开 `report.html` |
| 演示数据 | 验证安装、了解 PASS/FAIL 报告 | `robotdev demo ...` | 打开演示目录的 `index.html` |

桌面界面和 HTML 报告都是本地界面，不会启动云服务。无桌面的 Linux 服务器请使用终端模式。

### Windows 快速开始

推荐使用 **PowerShell**。先安装 64 位 Python 3.10–3.13，并在安装器中选中
“Add Python to PATH”和 Tcl/Tk。然后执行：

```powershell
# 1. 检查 Python
py -3.11 --version

# 2. 安装 pipx，并让 robotdev 命令进入 PATH
py -3.11 -m pip install --user pipx
py -3.11 -m pipx ensurepath

# 3. 关闭并重新打开 PowerShell，再从 GitHub 安装
pipx install git+https://github.com/1405264556/robotdev-tools.git

# 4A. 打开本地桌面界面
robotdev gui

# 4B. 或直接在终端分析；带中文和空格的路径必须加引号
robotdev analyze "D:\实验数据\run 01" `
  --config "D:\实验数据\robotdev.yaml" `
  --output "D:\实验报告\run 01"

# 5. 手动打开报告
Start-Process "D:\实验报告\run 01\report.html"
```

如果使用传统 CMD，分析命令相同，但换行符应使用 `^`，打开报告使用：

```bat
start "" "D:\实验报告\run 01\report.html"
```

若 PowerShell 提示找不到 `robotdev`，重新打开终端后运行 `pipx ensurepath`；仍有问题可直接使用：

```powershell
py -3.11 -m pipx run --spec git+https://github.com/1405264556/robotdev-tools.git robotdev --help
```

### Linux 快速开始

Ubuntu / Debian 桌面版：

```bash
# 1. 安装 Python、pipx；桌面界面额外需要 python3-tk
sudo apt update
sudo apt install python3 python3-pip pipx python3-tk
pipx ensurepath

# 2. 重新打开终端，安装 RobotDev Tools
pipx install git+https://github.com/1405264556/robotdev-tools.git

# 3A. 桌面环境中打开本地界面
robotdev gui

# 3B. 或使用终端分析
robotdev analyze "/data/实验记录/run 01" \
  --config "$HOME/robotdev.yaml" \
  --output "$HOME/reports/run-01"

# 4. 桌面环境中手动打开报告
xdg-open "$HOME/reports/run-01/report.html"
```

Fedora 桌面界面的 Tk 依赖为 `sudo dnf install python3-tkinter`。SSH、服务器或容器通常没有
图形显示环境，应直接使用 `robotdev analyze`，再把生成的 `report.html` 下载到本机浏览器查看。

### 可视化界面使用方法

运行 `robotdev gui` 后：

1. 在 **Bag 数据** 中选择标准 rosbag2 目录，或直接选择 `.db3` / `.mcap` 文件。
2. 在 **Config 门禁** 中选择质量门禁 YAML；可以留空，此时只计算指标，状态为 `NOT_EVALUATED`。
3. 在 **Output 报告** 中选择报告目录。
4. 点击 **开始分析**。分析在后台运行，界面不会上传数据。
5. 完成后默认打开 `report.html`；也可点击 **打开上次报告** 再次查看。

可以预填路径，减少重复选择：

```powershell
robotdev gui --bag "D:\bags\run 01" -c ".\robotdev.yaml" -o ".\report"
```

```bash
robotdev gui --bag "/data/bags/run-01" -c "./robotdev.yaml" -o "./report"
```

### 终端分析方法

```text
robotdev analyze BAG_PATH [--config CONFIG] [--output DIRECTORY] [--sample-limit N]
```

常见示例：

```bash
# 只计算指标，不执行 PASS/FAIL 门禁
robotdev analyze ./bag --output ./report

# 使用实验室门禁配置
robotdev analyze ./bag --config ./robotdev.yaml --output ./report

# 直接分析单个存储文件
robotdev analyze ./bag/rosbag2_0.db3 -c ./robotdev.yaml -o ./report
robotdev analyze ./bag/rosbag2_0.mcap -c ./robotdev.yaml -o ./report

# 限制每个 Topic 的图表采样点；不影响消息总数等在线统计
robotdev analyze ./large-bag -c ./robotdev.yaml -o ./report --sample-limit 10000
```

退出码可用于脚本和 CI：

| 退出码 | 含义 |
|---:|---|
| `0` | PASS、WARN，或未配置门禁的 `NOT_EVALUATED` |
| `2` | 至少一个硬性门禁 FAIL |
| `1` | 路径、配置或处理错误 |

### 安装、升级与卸载

推荐源码安装方式始终获取 GitHub 主分支的最新版本：

```bash
pipx install git+https://github.com/1405264556/robotdev-tools.git
pipx upgrade robotdev-tools
pipx uninstall robotdev-tools
```

如果需要固定版本，可从 [GitHub Releases](https://github.com/1405264556/robotdev-tools/releases)
下载 wheel，然后在文件所在目录执行：

```powershell
pipx install .\robotdev_tools-0.2.0-py3-none-any.whl
```

```bash
pipx install ./robotdev_tools-0.2.0-py3-none-any.whl
```

开发者从源码安装：

```bash
git clone https://github.com/1405264556/robotdev-tools.git
cd robotdev-tools
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -e ".[dev]"
# Linux:   .venv/bin/python -m pip install -e ".[dev]"
```

### 配置质量门禁

复制 [`examples/robotdev.yaml`](examples/robotdev.yaml)，再按机器人和传感器规格调整：

```yaml
version: 1
warn_margin_pct: 10

topics:
  /scan:
    required: true
    expected_rate_hz: 10
    rate_tolerance_pct: 10
    max_gap_ms: 250
    max_jitter_ms: 20

nodes:
  lidar_driver:
    required: true
    topics: [/scan]
  state_estimator:
    required: true
    topics: [/imu/data, /odom, /tf]

odometry:
  topic: /odom
  max_speed_mps: 1.5
  max_accel_mps2: 2.0
  max_position_jump_m: 0.5
```

- 必需 Topic 缺失或突破硬阈值：`FAIL`。
- 距离硬阈值不足 `warn_margin_pct`：`WARN`。
- 全部满足：`PASS`。
- 未传入配置：`NOT_EVALUATED`，避免把“仅完成分析”误认为“测试通过”。
- `nodes` 验证的是“该节点职责所需 Topic 是否被记录”，不是运行时进程名称。

> rosbag2 通常不保存发布者/订阅者对应的真实节点名称、服务、动作、参数和生命周期状态。
> 因此报告中的节点为 **INFERRED_FROM_BAG（从 bag 推断）**。若要证明实际 ROS 图，请在
> 机器人运行时配合 `ros2 node list`、`ros2 node info` 和 `ros2 topic info -v`。如果 bag
> 包含 `/rosout`，工具还会列出日志中自报的节点名称，但不会据此虚构发布/订阅边。

每次分析生成：

```text
report/
├── report.html    # 单文件、可离线打开的可视化报告
└── summary.json   # schema_version=1.1 的机器可读结果
```

详细参数解释、路径规则、CI 示例和故障排查见
[`docs/USAGE.zh-CN.md`](docs/USAGE.zh-CN.md)。

### 当前支持的检测内容

所有 Topic：消息数、观测时长、平均/中位频率、周期抖动、最大间隔、断流数、重复和
倒退时间戳。

| 子系统 | 标准消息 | 主要检测 |
|---|---|---|
| 激光雷达 | `LaserScan`、`PointCloud2` | 有效点比例、NaN/Inf、量程外点、扫描长度变化、空点云、frame |
| IMU | `Imu` | 角速度/加速度模长、四元数归一误差、不可用姿态、NaN/Inf |
| 里程计 | `Odometry` | XY 轨迹、里程/位移、线/角速度、加速度、位置跳变 |
| TF | `TFMessage` | 父子关系、根节点、连通分量、环、多父节点、非法四元数 |
| 控制指令 | `Twist`、`TwistStamped` | 最大线/角速度、活动/零指令比例、NaN/Inf |
| 关节状态 | `JointState` | 关节列表、数组长度不一致、关节集合变化、NaN/Inf |
| 定位结果 | `PoseWithCovarianceStamped`、`PoseStamped` | 位置跳变、协方差、frame、NaN/Inf |
| 规划轨迹 | `Path` | 空轨迹、点数、路径长度、frame 变化 |
| 故障状态 | `DiagnosticArray` | OK/WARN/ERROR/STALE 数量、受影响硬件、最新故障内容 |

报告包含实验总览、九类子系统健康卡、推断的 ROS 职责图与数据流、TF 关系图、质量门禁、
Topic 时序和里程计轨迹。未观察到的数据会标为缺失证据，不会伪造成节点故障。

### 数据规模

消息数、均值、标准差和最大值采用在线统计；图表和分位数默认每个流最多保留 20,000 点，
因此大 bag 不会因图表数据无限增长而耗尽内存。报告会明确标注是否发生采样。

### Python API

```python
from robotdev_tools import analyze_bag
from robotdev_tools.report import write_report

result = analyze_bag("/path/to/bag", "robotdev.yaml")
write_report(result, "report")
print(result.status, result.to_dict())
```

### 测试数据集与验收方法

仓库不提交二进制 bag；`robotdev demo` 会在本机生成三套确定性 ROS 2 测试数据和对应报告：

| 数据集 | 注入情况 | 预期状态 |
|---|---|---|
| `normal` | 九类 ROS 数据完整；TF 连通，运动和诊断正常 | `PASS` |
| `low_rate` | 激光雷达低频/断流并写入 Diagnostic WARN | `FAIL` |
| `jump` | 里程计/定位跳变并写入 Diagnostic ERROR | `FAIL` |

Windows：

```powershell
robotdev demo --output ".\robotdev-demo"
Start-Process ".\robotdev-demo\index.html"
Get-Content ".\robotdev-demo\normal\summary.json"
```

Linux：

```bash
robotdev demo --output ./robotdev-demo
xdg-open ./robotdev-demo/index.html
cat ./robotdev-demo/normal/summary.json
```

验收时确认正常报告为 PASS，两类故障报告为 FAIL，并检查 Topic 时序图、断流检查和里程计
轨迹是否与注入故障一致。完整的真实 bag 验收表、退出码检查和开发者测试命令见
[`docs/TESTING.md`](docs/TESTING.md)。

## English

RobotDev Tools is an automated ROS 2 rosbag2 analyzer, validator, diagnostics tool, and CI quality
gate for robotics teams. It reads SQLite3/DB3 and MCAP bags, evaluates Topic timing plus LiDAR, IMU,
odometry, TF, commands, joints, localization, paths, and diagnostics, then writes a self-contained
HTML report plus stable JSON.
The report reconstructs node responsibilities and data flow from recorded Topic/type evidence; it
does not claim to recover process-level node names that rosbag2 does not normally store.

Choose either workflow:

```bash
# Local desktop interface
robotdev gui

# Terminal / server / CI
robotdev analyze /path/to/rosbag2 --config examples/robotdev.yaml --output report

# Reproducible PASS and FAIL demo datasets
robotdev demo --output demo-output
```

Install from GitHub with `pipx`:

```bash
pipx install git+https://github.com/1405264556/robotdev-tools.git
```

On Ubuntu/Debian, install `python3-tk` before using the desktop interface. Headless Linux machines
should use `robotdev analyze`. Windows paths containing spaces or non-ASCII characters are supported;
quote them in PowerShell or CMD.

Supported: Python 3.10–3.13 on Windows/Linux, rosbag2 directories, raw `.db3`/`.mcap`, bounded-memory
topic timing metrics, nine ROS subsystem analyzers, inferred framework/TF views, and configurable
Topic-based node responsibility contracts. Analysis is local-only. Unknown custom messages retain
timing metrics when their payload cannot be decoded.

Read the [detailed Chinese guide](docs/USAGE.zh-CN.md), [test dataset and acceptance guide](docs/TESTING.md),
and [contribution guide](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
