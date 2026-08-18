import json
from pathlib import Path

from typer.testing import CliRunner

from robotdev_tools.analyzer import analyze_bag
from robotdev_tools.cli import app
from robotdev_tools.demo import generate_demo_bag
from robotdev_tools.report import write_report

runner = CliRunner()


def test_report_is_self_contained_and_json_is_compact(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "normal")
    result = analyze_bag(bag, Path(__file__).parents[1] / "examples" / "robotdev.yaml")
    result.bag.source = "<script>alert('x')</script>"
    html_path, json_path = write_report(result, tmp_path / "report")
    html = html_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "plotly.js" in html
    assert "&lt;script&gt;alert" in html
    assert "<script>alert('x')</script>" not in html
    assert "timeline_s" not in payload["topics"][0]
    assert "trajectory_x_m" not in payload["odometry"]
    assert payload["status"] == "PASS"


def test_cli_fail_exit_code_and_artifacts(tmp_path: Path) -> None:
    bag = generate_demo_bag(tmp_path / "jump", scenario="jump")
    output = tmp_path / "report"
    config = Path(__file__).parents[1] / "examples" / "robotdev.yaml"
    result = runner.invoke(
        app,
        ["analyze", str(bag), "--config", str(config), "--output", str(output)],
    )
    assert result.exit_code == 2
    assert "FAIL" in result.stdout
    assert (output / "report.html").is_file()
    assert (output / "summary.json").is_file()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
