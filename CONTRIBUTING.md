# Contributing

感谢你帮助改进 RobotDev Tools。Issues 可以使用中文或英文。

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Before submitting a change, run:

```bash
ruff check .
mypy src
pytest
python -m build
```

Please keep public JSON and YAML schemas backward compatible within the 0.1 series. New metrics
should include deterministic tests and must not require a ROS installation. Do not commit real
rosbags, credentials, personal data, or generated report directories.
