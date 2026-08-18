# RobotDev Tools

[中文](#中文) · [English](#english) · [详细使用指南](docs/USAGE.zh-CN.md) ·
[测试数据与验收](docs/TESTING.md)

![RobotDev Tools report preview](docs/images/report-preview.png)

## 中文

RobotDev Tools 是面向机器人实验室的 **ROS 2 离线实验验收工具**。它直接读取
rosbag2（SQLite3 / MCAP），自动计算 Topic 健康度和里程计运动指标，并生成
PASS / WARN / FAIL 质量门禁、自包含 HTML 可视化报告以及适合 CI 的 JSON 结果。

- 不需要安装 ROS 2。
- 数据只在本机处理，不上传 bag。
- Windows 和 Linux 均支持 Python 3.10–3.13。
- 可使用终端批处理，也可使用本地桌面界面选择文件。

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
pipx install .\robotdev_tools-0.1.0-py3-none-any.whl
```

```bash
pipx install ./robotdev_tools-0.1.0-py3-none-any.whl
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

每次分析生成：

```text
report/
├── report.html    # 单文件、可离线打开的可视化报告
└── summary.json   # schema_version=1.0 的机器可读结果
```

详细参数解释、路径规则、CI 示例和故障排查见
[`docs/USAGE.zh-CN.md`](docs/USAGE.zh-CN.md)。

### 指标与数据规模

所有 Topic：消息数、观测时长、平均/中位频率、周期抖动、最大间隔、断流数、重复和
倒退时间戳。

`nav_msgs/msg/Odometry`：XY 轨迹、累计里程、起终点位移、平均/最大/P95 线速度与角速度、
最大加速度、位置跳变及阈值违规次数。

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
| `normal` | 10 Hz `/scan` 与连续里程计 | `PASS` |
| `low_rate` | 低频和断流 | `FAIL` |
| `jump` | 里程计位置跳变及速度/加速度异常 | `FAIL` |

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

RobotDev Tools is a local, ROS-free experiment acceptance tool for robotics teams. It reads ROS 2
SQLite3 and MCAP bags, evaluates topic timing and odometry health, and writes a self-contained HTML
report plus stable JSON output.

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
topic timing metrics, and `nav_msgs/msg/Odometry` motion checks. Analysis is local-only. Unknown custom
messages retain timing metrics when their payload cannot be decoded.

Read the [detailed Chinese guide](docs/USAGE.zh-CN.md), [test dataset and acceptance guide](docs/TESTING.md),
and [contribution guide](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
