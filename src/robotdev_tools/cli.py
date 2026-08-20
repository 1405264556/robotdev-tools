"""RobotDev command-line interface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

import typer

from robotdev_tools import __version__
from robotdev_tools.analyzer import AnalysisError, analyze_bag
from robotdev_tools.config import ConfigError
from robotdev_tools.demo import generate_demo_bag
from robotdev_tools.discovery import discover_rosbags
from robotdev_tools.report import write_report

app = typer.Typer(
    name="robotdev",
    help="Automated ROS 2 rosbag2 analysis, validation, and diagnostics.",
    no_args_is_help=True,
    add_completion=False,
)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"robotdev {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Turn rosbag2 DB3/MCAP files into diagnostics and quality-gate reports."""


@app.command()
def analyze(
    bag_path: Annotated[Path, typer.Argument(help="rosbag2 directory, .db3, or .mcap")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Versioned robotdev YAML config")
    ] = None,
    output: Annotated[Path, typer.Option("--output", "-o", help="Report output directory")] = Path(
        "report"
    ),
    sample_limit: Annotated[
        int, typer.Option(help="Maximum retained chart points per topic")
    ] = 20_000,
) -> None:
    """Analyze one ROS 2 bag and write HTML plus JSON reports."""

    try:
        result = analyze_bag(bag_path, config, sample_limit=sample_limit)
        html_path, json_path = write_report(result, output)
    except (AnalysisError, ConfigError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{result.status}: {html_path}")
    typer.echo(f"JSON: {json_path}")
    if result.status == "FAIL":
        raise typer.Exit(code=2)


@app.command()
def discover(
    search_path: Annotated[
        Path, typer.Argument(help="File or directory to scan for rosbag2 recordings")
    ],
    max_depth: Annotated[int, typer.Option(help="Maximum recursive directory depth")] = 4,
    as_json: Annotated[
        bool, typer.Option("--json", help="Write machine-readable discovery results")
    ] = False,
) -> None:
    """Find rosbag2 recordings and identify DB3/MCAP plus Topic types."""

    try:
        candidates = discover_rosbags(search_path, max_depth=max_depth)
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if as_json:
        typer.echo(
            json.dumps(
                [candidate.to_dict() for candidate in candidates],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not candidates:
        typer.echo(f"No rosbag2 .db3 or .mcap recordings found under: {search_path}")
        return
    typer.echo(f"Found {len(candidates)} rosbag2 recording(s):")
    for candidate in candidates:
        state = "readable" if candidate.readable else f"error: {candidate.error}"
        topics = candidate.topic_count if candidate.topic_count is not None else "?"
        messages = candidate.message_count if candidate.message_count is not None else "?"
        duration = f"{candidate.duration_s:.3f}s" if candidate.duration_s is not None else "?"
        typer.echo(
            f"[{candidate.storage_format}] {topics} topics | {messages} messages | "
            f"{duration} | {state}\n  {candidate.path}"
        )


@app.command()
def demo(
    output: Annotated[Path, typer.Option("--output", "-o", help="Demo output directory")] = Path(
        "demo-output"
    ),
) -> None:
    """Generate normal and faulty bags plus ready-to-open reports."""

    if output.exists() and any(output.iterdir()):
        typer.echo(f"Error: demo output is not empty: {output}", err=True)
        raise typer.Exit(code=1)
    output.mkdir(parents=True, exist_ok=True)
    bundled_config = Path(__file__).resolve().parents[2] / "examples" / "robotdev.yaml"
    config_path = output / "robotdev.yaml"
    if bundled_config.exists():
        shutil.copyfile(bundled_config, config_path)
    else:
        config_path.write_text(
            "version: 1\nwarn_margin_pct: 10\ntopics:\n  /scan:\n    required: true\n"
            "    expected_rate_hz: 10\n    rate_tolerance_pct: 10\n    max_gap_ms: 250\n"
            "    max_jitter_ms: 20\nnodes:\n  lidar_driver:\n    required: true\n"
            "    topics: [/scan]\n  state_estimator:\n    required: true\n"
            "    topics: [/imu/data, /odom, /tf]\n  motion_controller:\n"
            "    required: true\n    topics: [/cmd_vel, /joint_states]\n"
            "  localization:\n    required: true\n    topics: [/amcl_pose]\n"
            "  planner:\n    required: true\n    topics: [/plan]\n  diagnostics:\n"
            "    required: true\n    topics: [/diagnostics]\nodometry:\n  topic: /odom\n"
            "  max_speed_mps: 1.5\n"
            "  max_accel_mps2: 2.0\n  max_position_jump_m: 0.5\n",
            encoding="utf-8",
        )
    try:
        statuses: list[tuple[str, str, Path]] = []
        for scenario in ("normal", "low_rate", "jump"):
            bag = generate_demo_bag(output / "bags" / scenario, scenario=scenario)
            result = analyze_bag(bag, config_path)
            html_path, _ = write_report(result, output / scenario)
            statuses.append((scenario, result.status, html_path))
        links = "\n".join(
            f"<li><strong>{name}</strong> — {status}: "
            f'<a href="{path.relative_to(output).as_posix()}">open report</a></li>'
            for name, status, path in statuses
        )
        (output / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>RobotDev demo</title>'
            "<style>body{font:16px system-ui;max-width:760px;margin:60px auto;"
            "line-height:1.6}</style>"
            f"<h1>RobotDev Tools demo</h1><ul>{links}</ul>",
            encoding="utf-8",
        )
    except (AnalysisError, ConfigError, OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Demo ready: {(output / 'index.html').resolve()}")


@app.command()
def gui(
    bag_path: Annotated[
        Path | None, typer.Option("--bag", help="Preselect a rosbag2 directory, .db3, or .mcap")
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Preselect a RobotDev YAML config")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Preselect the report output directory")
    ] = None,
) -> None:
    """Open the local desktop interface."""

    from robotdev_tools.gui import GUIUnavailableError, launch_gui

    try:
        launch_gui(bag_path=bag_path, config_path=config, output_path=output)
    except GUIUnavailableError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
