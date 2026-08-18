"""Self-contained HTML and compact JSON report generation."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import cast

import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

from robotdev_tools.models import AnalysisResult


def _topic_figure(result: AnalysisResult, *, include_plotlyjs: bool) -> str | None:
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
            full_html=False,
            include_plotlyjs="inline" if include_plotlyjs else False,
            config={"responsive": True},
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


def _framework_figure(result: AnalysisResult, *, include_plotlyjs: bool) -> str | None:
    framework = result.framework
    if framework is None or not framework.inferred_nodes:
        return None
    layers = {
        "lidar": 0,
        "imu": 0,
        "joint_states": 0,
        "odometry": 1,
        "tf": 1,
        "localization": 1,
        "planning": 2,
        "control": 3,
        "diagnostics": 4,
    }
    colors = {
        "HEALTHY": "#14805e",
        "DEGRADED": "#d97706",
        "FAULT": "#dc2626",
        "NO_DATA": "#64748b",
    }
    layer_counts: dict[int, int] = {}
    positions: dict[str, tuple[float, float]] = {}
    labels: dict[str, str] = {}
    for node in framework.inferred_nodes:
        role = node.node_id.split(":", 1)[0]
        x = float(layers.get(role, 2))
        index = layer_counts.get(int(x), 0)
        layer_counts[int(x)] = index + 1
        positions[node.node_id] = (x, float(-index))
        labels[node.node_id] = node.display_name.split(" / ", 1)[0]

    figure = go.Figure()
    for edge in framework.data_flows:
        if edge.source not in positions or edge.target not in positions:
            continue
        source = positions[edge.source]
        target = positions[edge.target]
        figure.add_trace(
            go.Scatter(
                x=[source[0], target[0]],
                y=[source[1], target[1]],
                mode="lines",
                line={"color": "#94a3b8", "width": 2},
                hovertemplate=edge.relation + "<extra></extra>",
                showlegend=False,
            )
        )
    for node in framework.inferred_nodes:
        position = positions[node.node_id]
        figure.add_trace(
            go.Scatter(
                x=[position[0]],
                y=[position[1]],
                mode="markers+text",
                marker={
                    "size": 34,
                    "color": colors[node.status],
                    "line": {"width": 2, "color": "white"},
                },
                text=[labels[node.node_id]],
                textposition="bottom center",
                customdata=[[node.responsibility, ", ".join(node.topics), node.status]],
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[0]}<br>Topics: %{customdata[1]}"
                    "<br>Status: %{customdata[2]}<extra></extra>"
                ),
                showlegend=False,
            )
        )
    figure.update_layout(
        title="Inferred ROS responsibility graph / 推断的 ROS 职责图",
        template="plotly_white",
        height=max(400, 170 + max(layer_counts.values(), default=1) * 85),
        margin={"l": 30, "r": 30, "t": 70, "b": 50},
        xaxis={
            "tickmode": "array",
            "tickvals": [0, 1, 2, 3, 4],
            "ticktext": [
                "Sensors / State",
                "Estimation / TF",
                "Planning",
                "Control",
                "Diagnostics",
            ],
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={"visible": False},
        hovermode="closest",
    )
    return cast(
        str,
        figure.to_html(
            full_html=False,
            include_plotlyjs="inline" if include_plotlyjs else False,
            config={"responsive": True},
        ),
    )


def _tf_figure(result: AnalysisResult, *, include_plotlyjs: bool) -> str | None:
    framework = result.framework
    if framework is None or not framework.frame_edges:
        return None
    edges = framework.frame_edges[:100]
    frames = sorted({value for edge in edges for value in (edge.parent, edge.child)})
    indices = {name: index for index, name in enumerate(frames)}
    figure = go.Figure(
        go.Sankey(
            arrangement="snap",
            node={"label": frames, "pad": 18, "thickness": 18, "color": "#3973c6"},
            link={
                "source": [indices[edge.parent] for edge in edges],
                "target": [indices[edge.child] for edge in edges],
                "value": [max(1, edge.message_count) for edge in edges],
                "label": ["static" if edge.is_static else "dynamic" for edge in edges],
                "color": [
                    "rgba(20,128,94,.28)" if edge.is_static else "rgba(57,115,198,.24)"
                    for edge in edges
                ],
            },
        )
    )
    figure.update_layout(
        title="Observed TF relations / 实际记录的 TF 关系",
        template="plotly_white",
        height=max(420, 180 + len(frames) * 25),
        margin={"l": 20, "r": 20, "t": 70, "b": 30},
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
    topic_figure = _topic_figure(result, include_plotlyjs=True)
    plotly_embedded = topic_figure is not None
    odometry_figure = _odometry_figure(result, include_plotlyjs=not plotly_embedded)
    plotly_embedded = plotly_embedded or odometry_figure is not None
    framework_figure = _framework_figure(result, include_plotlyjs=not plotly_embedded)
    plotly_embedded = plotly_embedded or framework_figure is not None
    tf_figure = _tf_figure(result, include_plotlyjs=not plotly_embedded)
    html = template.render(
        result=result,
        topic_figure=topic_figure,
        odometry_figure=odometry_figure,
        framework_figure=framework_figure,
        tf_figure=tf_figure,
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
