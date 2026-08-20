# RobotDev Tools 测试数据集与验收方法

本页用于验证安装是否正确、质量门禁是否能区分正常与故障数据，以及如何提交真实 bag 反馈。

## 1. 内置合成数据集

为了保持仓库轻量、避免 Git LFS 和平台下载差异，仓库不提交生成后的二进制 bag。
`robotdev demo` 会使用固定参数在本机生成可重复的小型 rosbag2 数据：

三套 bag 均包含 11 个 Topic、九类 ROS 职责数据：`/scan`、`/imu/data`、`/odom`、
`/tf`、`/tf_static`、`/cmd_vel`、`/joint_states`、`/amcl_pose`、`/plan` 和
`/diagnostics`，以及用于节点名称证据的 `/rosout`。

| 名称 | 故障注入 | 预期结果 | 专项表现 |
|---|---|---|---|
| `normal` | 无；传感器、运动、TF 和诊断连续 | PASS | 9 个子系统 HEALTHY，TF 单连通、无环 |
| `low_rate` | 激光扫描降至约 5 Hz，并插入断流 | FAIL | Topic rate/gap 失败，Diagnostics DEGRADED |
| `jump` | 里程计和定位瞬间偏移约 2 m | FAIL | Odometry FAULT、Localization DEGRADED、Diagnostics FAULT |

数据目录和报告目录一次生成：

```text
robotdev-demo/
├── bags/
│   ├── normal/
│   ├── low_rate/
│   └── jump/
├── normal/report.html
├── normal/summary.json
├── low_rate/report.html
├── low_rate/summary.json
├── jump/report.html
├── jump/summary.json
├── robotdev.yaml
└── index.html
```

## 2. Windows 验收

PowerShell：

```powershell
robotdev --version
robotdev demo --output ".\robotdev-demo"
Start-Process ".\robotdev-demo\index.html"
```

检查 JSON 状态：

```powershell
$normal = Get-Content ".\robotdev-demo\normal\summary.json" -Raw | ConvertFrom-Json
$lowRate = Get-Content ".\robotdev-demo\low_rate\summary.json" -Raw | ConvertFrom-Json
$jump = Get-Content ".\robotdev-demo\jump\summary.json" -Raw | ConvertFrom-Json
$normal.status
$lowRate.status
$jump.status
```

预期依次输出 `PASS`、`FAIL`、`FAIL`。

单独验证终端退出码：

```powershell
robotdev analyze ".\robotdev-demo\bags\normal" `
  -c ".\robotdev-demo\robotdev.yaml" -o ".\check-normal"
$LASTEXITCODE

robotdev analyze ".\robotdev-demo\bags\jump" `
  -c ".\robotdev-demo\robotdev.yaml" -o ".\check-jump"
$LASTEXITCODE
```

预期正常数据退出码为 `0`，跳变数据退出码为 `2`。

## 3. Linux 验收

```bash
robotdev --version
robotdev demo --output ./robotdev-demo
xdg-open ./robotdev-demo/index.html
```

服务器没有桌面时可直接读取 JSON：

```bash
python3 - <<'PY'
import json
from pathlib import Path

root = Path("robotdev-demo")
for name in ("normal", "low_rate", "jump"):
    data = json.loads((root / name / "summary.json").read_text())
    print(name, data["status"])
PY
```

检查退出码：

```bash
robotdev analyze ./robotdev-demo/bags/normal \
  -c ./robotdev-demo/robotdev.yaml -o ./check-normal
echo "normal exit code: $?"

robotdev analyze ./robotdev-demo/bags/jump \
  -c ./robotdev-demo/robotdev.yaml -o ./check-jump
echo "jump exit code: $?"
```

预期分别为 `0` 和 `2`。

## 4. 报告人工核对

打开 `index.html`，逐项检查：

### normal

- 总体状态为 PASS。
- `/scan` 频率接近期望值，最大间隔和抖动在阈值内。
- `/odom` XY 轨迹连续，无明显位置跳变。
- ROS Framework coverage 为 100%，显示九类推断职责。
- `/rosout` 节点名称证据显示 9 个合成节点名。
- TF 根为 `map`，关系包括 `map → odom → base_link` 及两个静态传感器 frame。
- LiDAR、IMU、Odometry、TF、Control、Joint states、Localization、Planning、Diagnostics
  均为 HEALTHY。
- Checks 中没有 FAIL。

### low_rate

- 总体状态为 FAIL。
- `/scan` 的频率检查和/或最大间隔检查为 FAIL。
- Topic 时序图能看到稀疏区间或断流。
- Diagnostics 卡显示 WARN：`Lidar update rate degraded`。
- 建议内容与低频/断流原因一致。

### jump

- 总体状态为 FAIL。
- XY 轨迹出现明显不连续。
- 位置跳变、速度或加速度相关检查至少一项为 FAIL。
- Localization 卡显示跳变，Diagnostics 卡显示 ERROR。
- HTML 指标与 `summary.json` 对应字段一致。

### JSON 快速核对

PowerShell 可直接查看新版结构：

```powershell
$r = Get-Content ".\robotdev-demo\normal\summary.json" -Raw | ConvertFrom-Json
$r.schema_version                  # 1.1
$r.subsystems | Select-Object subsystem_id, status, topics
$r.framework.inferred_nodes | Select-Object display_name, status, topics
$r.framework.frame_edges
```

Linux：

```bash
python3 - <<'PY'
import json
from pathlib import Path
r = json.loads(Path("robotdev-demo/normal/summary.json").read_text())
print(r["schema_version"])
print([(x["subsystem_id"], x["status"]) for x in r["subsystems"]])
print([(x["parent"], x["child"]) for x in r["framework"]["frame_edges"]])
PY
```

### 自动发现功能核对

```powershell
robotdev discover ".\robotdev-demo\bags"
robotdev discover ".\robotdev-demo\bags" --json
```

预期发现 `normal`、`low_rate`、`jump` 三个 SQLite3 bag；每个结果均为 11 Topics，JSON 中包含
`topic_types`。在 GUI 中选择 `robotdev-demo\bags`，应同屏出现三行并自动选中第一个可读结果。

## 5. 真实 bag 验收矩阵

建议至少使用三份真实数据：一份已知正常、一份传感器断流、一份运动异常或定位跳变。

| 检查项 | 数据/步骤 | 通过标准 |
|---|---|---|
| 安装 | Windows 与 Linux 各运行 `robotdev --version` | 命令可执行 |
| 格式 | `.db3` 与 `.mcap` 各分析一份 | 均生成 HTML/JSON |
| 自动发现 | 扫描包含多个嵌套 bag 的上级目录 | 正确列出路径、DB3/MCAP、Topic、消息数和时长 |
| 损坏输入 | 使用损坏 `.db3` 或 DB3/MCAP 混合目录 | 标记不可读，不允许误当正常 bag 分析 |
| 路径 | 使用含中文和空格的目录 | 不报路径错误 |
| 正常数据 | 使用实验室门禁分析 | PASS 或可解释的 WARN |
| 断流数据 | 移除/停止关键传感器 | required、rate 或 gap 为 FAIL |
| 轨迹异常 | 使用已知定位跳变数据 | jump/speed/accel 检查为 FAIL |
| ROS 职责 | 配置 `nodes.<name>.topics` | 所需 Topic 完整时 PASS，缺少必需证据时 FAIL |
| TF | 使用含 `/tf`、`/tf_static` 的 bag | 根、组件、环、多父关系与预期一致 |
| 九类专项 | 覆盖标准消息类型 | 对应子系统卡出现，指标和故障可解释 |
| 无配置 | 不传 `--config` | NOT_EVALUATED，退出码 0 |
| 未知类型 | 包含自定义 Topic | 保留时间指标，不导致整体崩溃 |
| 离线报告 | 断网后打开 HTML | 图表仍可用 |
| 安全 | bag 路径/元数据含 `<script>` 等文本 | 仅显示文本，不执行脚本 |

## 6. 反馈记录模板

不要在公开 Issue 上传含敏感信息的原始 bag。推荐提供匿名化后的 `summary.json` 和以下信息：

```text
系统：Windows 11 / Ubuntu 24.04 / ...
Python：3.11.x
存储格式：SQLite3 / MCAP
bag 大小与时长：
机器人/传感器类型：可匿名
使用方式：GUI / PowerShell / Bash / CI
预期结果：
实际结果：
是否重复使用：是 / 否；原因：
可公开的 summary.json：附加或粘贴关键字段
```

反馈入口：[GitHub Issues](https://github.com/1405264556/robotdev-tools/issues)。

## 7. 开发者测试

安装开发依赖：

```bash
python -m pip install -e ".[dev]"
```

运行全部检查：

```bash
ruff check .
mypy src/robotdev_tools
pytest --cov=robotdev_tools --cov-report=term-missing
python -m build
```

Windows 使用虚拟环境解释器时：

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src\robotdev_tools
.\.venv\Scripts\python -m pytest --cov=robotdev_tools --cov-report=term-missing
.\.venv\Scripts\python -m build
```

仓库的 GitHub Actions 会在 Ubuntu/Windows 和 Python 3.10–3.13 的八种组合上运行测试。

## 8. 自行构造专项故障的方法

对真实机器人建议一次只注入一种可恢复故障，并先确认不会造成安全风险：

- LiDAR：遮挡一部分视野或降低录制频率，观察有效点比例与断流。
- IMU：静止采集，确认重力模长和四元数稳定；不要通过物理冲撞制造异常。
- TF：在离线测试代码中构造断开的 frame 或多父 frame，不要修改生产 TF 树。
- Control：仅在架空轮或仿真环境验证零指令/活动比例和速度上限。
- JointState：在合成消息中删去一个 position 值，验证数组不一致检测。
- Localization/Odometry：使用合成 bag 注入坐标跳变，避免在真机强制重定位造成碰撞。
- Planning：生成空 `Path` 或 frame 变化的 `Path`。
- Diagnostics：生成 WARN、ERROR、STALE 各一条并确认报告计数和文本。

当前内置 demo 的二进制 bag 每次由代码生成，不提交仓库，因此 SQLite3/MCAP 内容可复现且不会
因为大文件或 Git LFS 影响安装。
