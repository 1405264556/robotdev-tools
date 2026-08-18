"""Self-contained HTML and compact JSON report generation."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import cast

import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

from robotdev_tools.models import AnalysisResult


def _topic_figure(result: AnalysisResult) -> str | None:
    available = [topic for topic in result.topics if topic.timeline_s]
    if not available:
        return None
    figure = go.Figure()
    for row, topic in enumerate(available):
        figure.add_trace(
            go.Scattergl(
                x=topic.timeline_s,
                y=[row] * len(topic.timeline_s),
                mode="markers",
                marker={"size": 5, "opacity": 0.65},
                name=topic.name,
                hovertemplate=f"{topic.name}<br>t=%{{x:.3f}} s<extra></extra>",
            )
        )
    figure.update_layout(
        title="Topic message timeline / Topic 消息时间线",
        xaxis_title="Time since bag start (s)",
        yaxis={
            "tickmode": "array",
            "tickvals": list(range(len(available))),
            "ticktext": [topic.name for topic in available],
        },
        template="plotly_white",
        height=max(320, 75 + 48 * len(available)),
        margin={"l": 120, "r": 24, "t": 65, "b": 60},
        showlegend=False,
    )
    return cast(
        str,
        figure.to_html(
            full_html=False, include_plotlyjs="inline", config={"responsive": True}
        ),
    )


def _odometry_figure(result: AnalysisResult, *, include_plotlyjs: bool) -> str | None:
    odometry = result.odometry
    if odometry is None or not odometry.trajectory_x_m:
        return None
    figure = go.Figure(
        go.Scattergl(
            x=odometry.trajectory_x_m,
            y=odometry.trajectory_y_m,
            mode="lines+markers",
            marker={"size": 4, "color": odometry.trajectory_time_s, "colorscale": "Viridis"},
            line={"color": "#3578e5", "width": 2},
            hovertemplate="x=%{x:.3f} m<br>y=%{y:.3f} m<extra></extra>",
        )
    )
    figure.update_layout(
        title=f"Odometry trajectory / 里程计轨迹 · {odometry.topic}",
        xaxis_title="X (m)",
        yaxis_title="Y (m)",
        yaxis={"scaleanchor": "x", "scaleratio": 1},
        template="plotly_white",
        height=480,
        margin={"l": 70, "r": 24, "t": 65, "b": 60},
    )
    return cast(
        str,
        figure.to_html(
            full_html=False,
            include_plotlyjs="inline" if include_plotlyjs else False,
            config={"responsive": True},
        ),
    )


def write_report(result: AnalysisResult, output: str | Path) -> tuple[Path, Path]:
    """Write ``report.html`` and ``summary.json`` into ``output``."""

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    template_dir = files("robotdev_tools").joinpath("templates")
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("report.html.j2")
    topic_figure = _topic_figure(result)
    odometry_figure = _odometry_figure(result, include_plotlyjs=topic_figure is None)
    html = template.render(
        result=result,
        topic_figure=topic_figure,
        odometry_figure=odometry_figure,
        sampled=any(topic.message_count > topic.sampled_points for topic in result.topics),
    )
    html_path = output_dir / "report.html"
    json_path = output_dir / "summary.json"
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return html_path, json_path
