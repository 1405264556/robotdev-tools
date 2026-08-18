# RobotDev Tools 测试数据集与验收方法

本页用于验证安装是否正确、质量门禁是否能区分正常与故障数据，以及如何提交真实 bag 反馈。

## 1. 内置合成数据集

为了保持仓库轻量、避免 Git LFS 和平台下载差异，仓库不提交生成后的二进制 bag。
`robotdev demo` 会使用固定参数在本机生成可重复的小型 rosbag2 数据：

| 名称 | Topic | 故障注入 | 预期结果 |
|---|---|---|---|
| `normal` | `/scan`、`/odom` | 无；扫描约 10 Hz，轨迹连续 | PASS |
| `low_rate` | `/scan`、`/odom` | 扫描低频并包含明显断流 | FAIL |
| `jump` | `/scan`、`/odom` | 里程计位置瞬间跳变，导致速度/加速度异常 | FAIL |

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
- Checks 中没有 FAIL。

### low_rate

- 总体状态为 FAIL。
- `/scan` 的频率检查和/或最大间隔检查为 FAIL。
- Topic 时序图能看到稀疏区间或断流。
- 建议内容与低频/断流原因一致。

### jump

- 总体状态为 FAIL。
- XY 轨迹出现明显不连续。
- 位置跳变、速度或加速度相关检查至少一项为 FAIL。
- HTML 指标与 `summary.json` 对应字段一致。

## 5. 真实 bag 验收矩阵

建议至少使用三份真实数据：一份已知正常、一份传感器断流、一份运动异常或定位跳变。

| 检查项 | 数据/步骤 | 通过标准 |
|---|---|---|
| 安装 | Windows 与 Linux 各运行 `robotdev --version` | 命令可执行 |
| 格式 | `.db3` 与 `.mcap` 各分析一份 | 均生成 HTML/JSON |
| 路径 | 使用含中文和空格的目录 | 不报路径错误 |
| 正常数据 | 使用实验室门禁分析 | PASS 或可解释的 WARN |
| 断流数据 | 移除/停止关键传感器 | required、rate 或 gap 为 FAIL |
| 轨迹异常 | 使用已知定位跳变数据 | jump/speed/accel 检查为 FAIL |
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
