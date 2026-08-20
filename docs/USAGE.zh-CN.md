# RobotDev Tools 详细使用指南

本指南覆盖 Windows、Linux、终端和桌面界面四种使用环境。RobotDev Tools 的分析过程和
报告生成全部发生在本机，不需要 ROS 2，也不会上传 rosbag2。

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| Python | 3.10、3.11、3.12 或 3.13，推荐 3.11/3.12 |
| 系统 | Windows 10/11；常见 x86-64 Linux 发行版 |
| ROS | 不需要 |
| 浏览器 | 用于打开生成的自包含 HTML 报告 |
| 桌面界面 | Windows Python 通常自带；Linux 需安装 Tkinter |

支持的输入形式：

- 标准 rosbag2 目录：包含 `metadata.yaml` 和一个或多个存储文件。
- SQLite3 存储文件：扩展名为 `.db3`。
- MCAP 存储文件：扩展名为 `.mcap`。
- Windows/Linux 中带空格、中文或其他 Unicode 字符的路径。
- 选择 `metadata.yaml` 时自动使用它所在的标准 rosbag2 目录。
- 选择实验数据上级目录时，自动递归发现其中的多个 bag。

## 2. Windows 安装

### 2.1 安装 Python 与 pipx

从 [python.org](https://www.python.org/downloads/windows/) 安装 64 位 Python。若要使用
`robotdev gui`，安装器中的 Tcl/Tk 组件不能取消。打开 PowerShell：

```powershell
py --list
py -3.11 --version
py -3.11 -m pip install --user --upgrade pip pipx
py -3.11 -m pipx ensurepath
```

关闭并重新打开 PowerShell，让 PATH 设置生效。然后安装：

```powershell
pipx install git+https://github.com/1405264556/robotdev-tools.git
robotdev --version
robotdev --help
```

若实验室机器不允许修改 PATH，可以使用下面的临时运行方式：

```powershell
py -3.11 -m pipx run --spec git+https://github.com/1405264556/robotdev-tools.git robotdev --help
```

### 2.2 PowerShell、CMD 路径差异

PowerShell 多行命令使用反引号，CMD 使用 `^`。路径包含空格或中文时，两者都应加双引号。

PowerShell：

```powershell
robotdev analyze "D:\实验数据\导航实验 01" `
  -c "D:\实验配置\robotdev.yaml" `
  -o "D:\实验报告\导航实验 01"
$LASTEXITCODE
Start-Process "D:\实验报告\导航实验 01\report.html"
```

CMD：

```bat
robotdev analyze "D:\实验数据\导航实验 01" ^
  -c "D:\实验配置\robotdev.yaml" ^
  -o "D:\实验报告\导航实验 01"
echo %ERRORLEVEL%
start "" "D:\实验报告\导航实验 01\report.html"
```

## 3. Linux 安装

### 3.1 Ubuntu / Debian

```bash
sudo apt update
sudo apt install python3 python3-pip pipx
pipx ensurepath
pipx install git+https://github.com/1405264556/robotdev-tools.git
robotdev --version
```

桌面界面额外安装：

```bash
sudo apt install python3-tk
robotdev gui
```

### 3.2 Fedora

```bash
sudo dnf install python3 pipx
pipx ensurepath
pipx install git+https://github.com/1405264556/robotdev-tools.git
```

桌面界面额外安装：

```bash
sudo dnf install python3-tkinter
```

### 3.3 服务器或 SSH

无图形桌面时不要运行 `robotdev gui`。直接分析并把 HTML 下载到本机：

```bash
robotdev analyze /data/bags/run-01 \
  -c /opt/robotdev/robotdev.yaml \
  -o /data/reports/run-01
echo $?
```

例如从自己的电脑下载报告：

```bash
scp user@robot-server:/data/reports/run-01/report.html ./run-01-report.html
```

`report.html` 已内嵌 Plotly 和全部数据，查看时不需要服务器或互联网。

## 4. 桌面界面

### 4.1 启动

```bash
robotdev gui
```

也可以预填路径：

```bash
robotdev gui --bag /data/bags/run-01 -c ./robotdev.yaml -o ./reports/run-01
```

界面字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| 文件或扫描目录 | 是 | `.db3`、`.mcap`、`metadata.yaml`、bag 目录或多次实验的上级目录 |
| 候选表格 | 是 | 显示格式、输入类型、Topic 数、消息数、时长和路径；选择一行作为分析输入 |
| Topic 类型预览 | 自动 | 显示识别到的 Topic 与标准消息类型，不读取消息载荷 |
| Config 门禁 | 否 | 版本化门禁配置；留空则结果为 `NOT_EVALUATED` |
| Output 报告 | 是 | 保存 `report.html` 和 `summary.json` 的目录 |
| 完成后打开报告 | 否 | 分析完成后用系统默认浏览器打开报告 |

选择文件后会立即识别；选择目录后最多递归 4 层并合并同一目录中的拆分存储文件。扫描只打开
bag 索引，不反序列化消息内容，因此可以先快速比较多次实验。损坏文件、SQLite3/MCAP 混放等
情况会显示明确错误并禁止开始分析。

点击 **开始分析并生成报告** 后，完整读取和统计在后台线程执行。状态栏会显示最终状态和两个输出文件。
输出目录可以已存在；同名报告文件会被新结果替换，因此建议每次实验使用独立目录。

桌面窗口负责选择输入和启动任务；详细结果会在完成后打开的本地 HTML 中显示。HTML 不只是
PASS/FAIL 结果页，还包括 ROS 职责框架、子系统健康卡、TF 拓扑、Topic 时序和运动轨迹。

### 4.2 界面无法启动

- Windows 出现 Tcl/Tk 错误：使用 python.org 安装器修改 Python，启用 Tcl/Tk。
- Ubuntu/Debian 提示 Tkinter 缺失：`sudo apt install python3-tk`。
- Fedora：`sudo dnf install python3-tkinter`。
- Linux 提示没有 graphical desktop/display：当前为 SSH 或无桌面会话，改用终端模式。

## 5. 终端命令

### 5.1 discover

```text
robotdev discover SEARCH_PATH [--max-depth N] [--json]
```

它用于在分析前发现并识别 rosbag2：

```powershell
# Windows：扫描包含多次实验的目录
robotdev discover "F:\实验数据"

# 输出 JSON，供脚本筛选路径和存储格式
robotdev discover "F:\实验数据" --json
```

```bash
# Linux
robotdev discover /data/experiments
robotdev discover /data/experiments --max-depth 2 --json
```

识别结果包含 `storage_format`、`input_kind`、`storage_files`、`metadata_present`、文件大小、
消息数、时长以及完整 Topic/消息类型。此命令不执行质量门禁，也不生成报告。

### 5.2 analyze

```text
robotdev analyze BAG_PATH [OPTIONS]

Options:
  -c, --config PATH       RobotDev YAML 配置
  -o, --output PATH       输出目录，默认 report
      --sample-limit N    每个 Topic 最多保留的图表点数，默认 20000
```

不带配置：

```bash
robotdev analyze ./bag -o ./report
```

这会生成完整指标，但总体状态为 `NOT_EVALUATED`。只有明确提供阈值配置后才会出现 PASS/WARN/FAIL。

带配置：

```bash
robotdev analyze ./bag -c ./robotdev.yaml -o ./report
```

### 5.3 demo

```bash
robotdev demo --output ./robotdev-demo
```

输出目录必须为空，避免误覆盖现有数据。该命令生成 `normal`、`low_rate` 和 `jump` 三套
合成 bag、配置、三份报告以及总入口 `index.html`。

### 5.4 gui

```text
robotdev gui [--bag PATH] [-c CONFIG] [-o OUTPUT]
```

它只是对同一个 `analyze_bag` 接口的本地桌面封装，指标和终端模式完全一致。

## 6. 配置说明

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
  navigation:
    required: true
    topics: [/amcl_pose, /plan, /cmd_vel]

odometry:
  topic: /odom
  max_speed_mps: 1.5
  max_accel_mps2: 2.0
  max_position_jump_m: 0.5
```

建议为不同机器人或实验类型分别保存配置，例如：

```text
configs/
├── mobile-base-indoor.yaml
├── mobile-base-outdoor.yaml
└── nav2-regression.yaml
```

阈值应来自设备规格、历史正常实验分布和任务安全边界，而不是直接复制示例值。先用无配置模式
分析 5–10 次正常实验，再设置预期频率、间隔和运动上限会更可靠。

### 6.1 节点职责检测的含义

普通 rosbag2 记录消息，却通常不记录每条连接对应的真实发布者/订阅者节点名称，也不保存完整
服务、动作、参数和生命周期图。因此离线报告采用两层表达：

1. **自动推断职责**：根据标准消息类型识别激光、IMU、里程计、TF、控制、关节、定位、规划
   和诊断职责，显示 `INFERRED_FROM_BAG`。
2. **日志节点名证据**：若录制了 `/rosout`（`rcl_interfaces/msg/Log`），报告列出消息 `name`
   中节点自报的名称，但它不能证明全程存活，也不能恢复发布/订阅边。
3. **配置职责合同**：`nodes.<name>.topics` 要求某个逻辑职责的 Topic 证据完整。必需合同缺少
   任意 Topic 时为 FAIL，可选合同缺失时为 WARN。

例如 `state_estimator` 合同通过，仅表示 `/imu/data`、`/odom`、`/tf` 确实被录入 bag；它不证明
运行时进程恰好叫 `/state_estimator`。需要真实节点图时，在实验运行期间另行保存：

```bash
ros2 node list
ros2 node info /node_name
ros2 topic info /topic_name -v
```

## 7. 输出解释

`report.html` 的主要区域：

| 区域 | 用途 |
|---|---|
| Experiment overview | 总体门禁、bag 时长/消息数、九类职责覆盖率 |
| ROS framework analysis | 从 Topic/类型推断的职责节点、数据流和缺失子系统 |
| Subsystem diagnostics | 激光、IMU、里程计、TF、控制、关节、定位、规划、故障逐项指标 |
| TF tree analysis | 父子 frame、根节点、连通分量、环、多父节点和静态/动态关系 |
| Quality gates | 配置阈值、实测值、PASS/WARN/FAIL 和修复建议 |
| Topic timing | 全量 Topic 的频率、抖动、最大间隔、断流和时间戳问题 |
| Odometry trajectory | 可交互 XY 轨迹及运动极值 |

报告是自包含文件，可直接发给同事；但其中可能包含 Topic 名称、bag 路径、frame 名和故障文本，
外发前仍应检查敏感信息。

`summary.json` 用于程序处理，顶层至少包含：

- `schema_version`
- bag 元数据
- Topic 指标
- odometry 指标（可用时）
- `subsystems` 九类专项检测结果
- `framework` 推断职责、数据流和 TF 拓扑
- checks
- 总体 `status`

### 7.1 九类专项检测

| 类别 | 识别类型 | 输出重点 |
|---|---|---|
| LiDAR | `sensor_msgs/msg/LaserScan`、`PointCloud2` | 点/束数、有效比例、NaN/Inf、量程外点、扫描长度一致性、空点云 |
| IMU | `sensor_msgs/msg/Imu` | 角速度和加速度模长、四元数误差、姿态不可用、非有限值 |
| Odometry | `nav_msgs/msg/Odometry` | 距离/位移、速度分位数、加速度、跳变和轨迹 |
| TF | `tf2_msgs/msg/TFMessage` | frame 边、根、组件、环、多父节点、非法旋转 |
| Control | `geometry_msgs/msg/Twist`、`TwistStamped` | 活动比例、零指令、最大线/角速度、非有限值 |
| Joint states | `sensor_msgs/msg/JointState` | 关节名称、字段长度、集合变化、非有限值 |
| Localization | `PoseWithCovarianceStamped`、`PoseStamped` | 跳变、协方差、frame 一致性、非有限值 |
| Planning | `nav_msgs/msg/Path` | 空规划、轨迹点数、路径长度、frame 一致性 |
| Diagnostics | `diagnostic_msgs/msg/DiagnosticArray` | OK/WARN/ERROR/STALE、受影响硬件和最新故障 |

专项卡的 `HEALTHY/DEGRADED/FAULT/NO_DATA` 是数据诊断结论；顶层 `PASS/WARN/FAIL` 则由 YAML
质量门禁决定。未配置门禁时，即使专项卡健康，顶层仍是 `NOT_EVALUATED`。

退出码：

- `0`：PASS、WARN、NOT_EVALUATED。
- `2`：FAIL。
- `1`：输入、配置或处理错误。

Linux CI 示例：

```bash
set +e
robotdev analyze "$BAG_PATH" -c robotdev.yaml -o artifacts/robotdev
code=$?
set -e
test "$code" -eq 0
```

PowerShell 自动化示例：

```powershell
robotdev analyze $env:BAG_PATH -c robotdev.yaml -o artifacts\robotdev
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## 8. 更新和清理

```bash
pipx upgrade robotdev-tools
pipx reinstall robotdev-tools
pipx uninstall robotdev-tools
```

工具不会写入 bag 目录。删除不再需要的报告目录和 demo 目录即可清理输出。

## 9. 常见问题

### 为什么没有配置时不是 PASS？

因为没有门禁阈值就不能证明实验合格，`NOT_EVALUATED` 可以避免产生错误的通过结论。

### 自定义消息类型会导致整个分析失败吗？

通常不会。无法反序列化的自定义类型仍保留消息数、时间范围、频率、间隔等无需解码的指标；
只有需要消息字段的专项指标会降级并给出提示。

### 能直接读取正在录制的 bag 吗？

不建议。应在 rosbag2 正常关闭并写完 metadata 后分析，避免 SQLite 锁和不完整消息造成误判。

### 为什么大 bag 的图表点数少于消息数？

图表使用最多 20,000 点的确定性采样，消息总数、均值和极值等核心统计仍在线计算。

### 是否支持 ROS 1、ATE/RPE 或实时节点？

当前版本不支持。这些功能属于后续路线图。

## 10. 测试数据和验收

首次安装后建议先运行合成数据验收，再分析真实实验：

```bash
robotdev demo --output ./robotdev-demo
```

三套数据都包含激光、IMU、里程计、TF、控制指令、关节状态、定位、规划和诊断消息。
预期 `normal=PASS`、`low_rate=FAIL`、`jump=FAIL`。完整检查步骤和真实 bag 反馈模板见
[`TESTING.md`](TESTING.md)。
