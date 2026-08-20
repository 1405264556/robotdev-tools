"""Local desktop interface with automatic rosbag2 discovery and type preview."""

from __future__ import annotations

import os
import platform
import threading
import webbrowser
from pathlib import Path

from robotdev_tools.analyzer import AnalysisError, analyze_bag
from robotdev_tools.config import ConfigError
from robotdev_tools.discovery import BagCandidate, discover_rosbags
from robotdev_tools.report import write_report


class GUIUnavailableError(RuntimeError):
    """Raised when the optional Tk desktop runtime is unavailable."""


def tkinter_install_hint() -> str:
    """Return a platform-specific hint for installing Tkinter."""

    if platform.system() == "Linux":
        return (
            "Tkinter is not installed. On Ubuntu/Debian run "
            "'sudo apt install python3-tk'; on Fedora run 'sudo dnf install python3-tkinter'."
        )
    return "Tkinter is unavailable. Reinstall Python from python.org with the Tcl/Tk option."


def format_size(size_bytes: int) -> str:
    """Format a byte size for compact GUI presentation."""

    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def candidate_summary(candidate: BagCandidate) -> str:
    """Build a bilingual one-line recognition summary."""

    format_names = {
        "sqlite3": "SQLite3 / DB3",
        "mcap": "MCAP",
        "mixed": "Mixed / 混合格式",
        "unknown": "Unknown / 未知",
    }
    kind_names = {
        "standard_directory": "标准 rosbag2 目录",
        "storage_directory": "存储文件目录",
        "raw_file": "单个存储文件",
        "unknown": "未知输入",
    }
    if not candidate.readable:
        return (
            f"识别失败 · {format_names[candidate.storage_format]} · "
            f"{candidate.error or 'Unknown error'}"
        )
    topics = candidate.topic_count or 0
    messages = candidate.message_count or 0
    duration = candidate.duration_s or 0.0
    return (
        f"已识别 {format_names[candidate.storage_format]} · {kind_names[candidate.input_kind]} · "
        f"{len(candidate.storage_files)} 个存储文件 · {topics} Topics · "
        f"{messages:,} 条消息 · {duration:.3f} 秒 · {format_size(candidate.size_bytes)}"
    )


def topic_preview(candidate: BagCandidate, *, limit: int = 5) -> str:
    """Return a compact preview of detected Topic/message types."""

    visible = candidate.topic_types[:limit]
    text = "  ·  ".join(f"{item.topic} [{item.message_type}]" for item in visible)
    remaining = len(candidate.topic_types) - len(visible)
    if remaining > 0:
        text += f"  ·  +{remaining} more"
    return text or "未读取到 Topic 类型 / No Topic types detected"


def launch_gui(
    bag_path: Path | None = None,
    config_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Launch the local Tk desktop interface."""

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter import font as tkfont
    except ImportError as exc:  # pragma: no cover - depends on the host Python build
        raise GUIUnavailableError(tkinter_install_hint()) from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on desktop/display availability
        raise GUIUnavailableError(
            "A graphical desktop is not available. Use 'robotdev analyze' in the terminal, "
            "or run 'robotdev gui' inside a desktop session."
        ) from exc

    root.title("RobotDev Tools · ROSBag2 Auto Detector")
    root.geometry("1080x780")
    root.minsize(860, 680)

    initial_source = str(bag_path or "")
    default_output = output_path or Path.cwd() / "robotdev-report"
    source_var = tk.StringVar(value=initial_source)
    bag_var = tk.StringVar(value=initial_source)
    config_var = tk.StringVar(value=str(config_path or ""))
    output_var = tk.StringVar(value=str(default_output))
    open_report_var = tk.BooleanVar(value=True)
    detection_var = tk.StringVar(
        value="选择文件或目录后自动识别 SQLite3/DB3、MCAP 和 Topic 消息类型。"
    )
    selected_var = tk.StringVar(value="尚未选择可分析的 rosbag2。")
    topics_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Ready / 就绪")
    last_report: dict[str, Path | None] = {"path": None}
    candidates_by_id: dict[str, BagCandidate] = {}
    output_user_selected = output_path is not None

    style = ttk.Style(root)
    if "vista" in style.theme_names() and os.name == "nt":
        style.theme_use("vista")
    title_font = tkfont.nametofont("TkDefaultFont").copy()
    title_font.configure(size=20, weight="bold")
    subtitle_font = tkfont.nametofont("TkDefaultFont").copy()
    subtitle_font.configure(size=10)
    selected_font = tkfont.nametofont("TkDefaultFont").copy()
    selected_font.configure(weight="bold")
    style.configure("Title.TLabel", font=title_font, foreground="#12355b")
    style.configure("Subtitle.TLabel", font=subtitle_font, foreground="#526276")
    style.configure("Selected.TLabel", font=selected_font, foreground="#0f6b4f")
    style.configure("Status.TLabel", foreground="#1d4ed8")
    style.configure("Primary.TButton", font=("TkDefaultFont", 10, "bold"))

    frame = ttk.Frame(root, padding=(24, 18))
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)

    ttk.Label(
        frame,
        text="RobotDev Tools · ROSBag2 自动检测",
        style="Title.TLabel",
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text=(
            "自动发现 rosbag2、识别 DB3/MCAP 与消息类型, 然后生成 ROS 框架和质量报告 · "
            "Local only, no ROS install, no upload"
        ),
        style="Subtitle.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(3, 14))

    source_box = ttk.LabelFrame(
        frame, text=" 1. 自动发现与类型识别 / Discover rosbag2 ", padding=12
    )
    source_box.grid(row=2, column=0, sticky="nsew")
    source_box.columnconfigure(1, weight=1)
    source_box.rowconfigure(3, weight=1)

    ttk.Label(source_box, text="文件或扫描目录").grid(row=0, column=0, sticky="w")
    source_entry = ttk.Entry(source_box, textvariable=source_var)
    source_entry.grid(row=0, column=1, sticky="ew", padx=10)

    discovery_progress = ttk.Progressbar(source_box, mode="indeterminate")
    discovery_progress.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 5))

    columns = ("format", "kind", "topics", "messages", "duration", "path")
    tree = ttk.Treeview(source_box, columns=columns, show="headings", height=7)
    headings = {
        "format": "存储格式",
        "kind": "输入类型",
        "topics": "Topics",
        "messages": "消息数",
        "duration": "时长",
        "path": "路径",
    }
    widths = {
        "format": 105,
        "kind": 120,
        "topics": 70,
        "messages": 90,
        "duration": 80,
        "path": 470,
    }
    for column in columns:
        tree.heading(column, text=headings[column])
        tree.column(column, width=widths[column], minwidth=55, stretch=column == "path")
    tree.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(4, 8))
    tree.tag_configure("error", foreground="#b42318")
    tree_scroll = ttk.Scrollbar(source_box, orient="vertical", command=tree.yview)
    tree_scroll.grid(row=3, column=4, sticky="ns", pady=(4, 8))
    tree.configure(yscrollcommand=tree_scroll.set)

    ttk.Label(source_box, textvariable=detection_var, style="Subtitle.TLabel").grid(
        row=4, column=0, columnspan=5, sticky="w"
    )
    ttk.Label(source_box, textvariable=selected_var, style="Selected.TLabel").grid(
        row=5, column=0, columnspan=5, sticky="w", pady=(6, 0)
    )
    ttk.Label(
        source_box,
        textvariable=topics_var,
        style="Subtitle.TLabel",
        wraplength=970,
        justify="left",
    ).grid(row=6, column=0, columnspan=5, sticky="w", pady=(4, 0))

    def choose_bag_file() -> None:
        selected = filedialog.askopenfilename(
            title="Select rosbag2 DB3, MCAP, or metadata.yaml",
            filetypes=[
                ("ROS 2 bags", "*.db3 *.mcap metadata.yaml"),
                ("SQLite3", "*.db3"),
                ("MCAP", "*.mcap"),
                ("rosbag2 metadata", "metadata.yaml"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            source_var.set(selected)
            start_discovery()

    def choose_scan_folder() -> None:
        selected = filedialog.askdirectory(title="Select directory to scan for rosbag2")
        if selected:
            source_var.set(selected)
            start_discovery()

    file_button = ttk.Button(source_box, text="选择文件…", command=choose_bag_file)
    file_button.grid(row=0, column=2, padx=(0, 6))
    folder_button = ttk.Button(source_box, text="选择目录并扫描…", command=choose_scan_folder)
    folder_button.grid(row=0, column=3, padx=(0, 6))

    def select_candidate(candidate_id: str) -> None:
        candidate = candidates_by_id[candidate_id]
        bag_var.set(str(candidate.path))
        selected_var.set(candidate_summary(candidate))
        topics_var.set(topic_preview(candidate))
        if not output_user_selected:
            report_name = f"{candidate.path.stem}-robotdev-report"
            output_var.set(str(candidate.path.parent / report_name))
        if candidate.readable:
            analyze_button.state(["!disabled"])
        else:
            analyze_button.state(["disabled"])

    def on_tree_selection(_event: object | None = None) -> None:
        selection = tree.selection()
        if selection:
            select_candidate(selection[0])

    tree.bind("<<TreeviewSelect>>", on_tree_selection)
    tree.bind("<Double-1>", on_tree_selection)

    def finish_discovery(candidates: list[BagCandidate], error: str | None = None) -> None:
        discovery_progress.stop()
        file_button.state(["!disabled"])
        folder_button.state(["!disabled"])
        scan_button.state(["!disabled"])
        for item in tree.get_children():
            tree.delete(item)
        candidates_by_id.clear()
        bag_var.set("")
        analyze_button.state(["disabled"])
        if error is not None:
            detection_var.set(f"识别失败 / Discovery failed: {error}")
            selected_var.set("尚未选择可分析的 rosbag2。")
            topics_var.set("")
            return
        if not candidates:
            detection_var.set("未发现 .db3、.mcap 或标准 rosbag2 目录。可更换目录后重试。")
            selected_var.set("No rosbag2 selected / 尚未选择 rosbag2")
            topics_var.set("")
            return
        readable_count = sum(candidate.readable for candidate in candidates)
        detection_var.set(
            f"发现 {len(candidates)} 个候选, 其中 {readable_count} 个可读取; 选择一行后分析。"
        )
        for index, candidate in enumerate(candidates):
            candidate_id = f"bag-{index}"
            candidates_by_id[candidate_id] = candidate
            duration = f"{candidate.duration_s:.2f}s" if candidate.duration_s is not None else "—"
            tree.insert(
                "",
                "end",
                iid=candidate_id,
                values=(
                    candidate.storage_format.upper(),
                    candidate.input_kind.replace("_", " "),
                    candidate.topic_count if candidate.topic_count is not None else "—",
                    f"{candidate.message_count:,}" if candidate.message_count is not None else "—",
                    duration,
                    str(candidate.path),
                ),
                tags=() if candidate.readable else ("error",),
            )
        preferred = next(
            (item_id for item_id, item in candidates_by_id.items() if item.readable),
            next(iter(candidates_by_id)),
        )
        tree.selection_set(preferred)
        tree.focus(preferred)
        tree.see(preferred)
        select_candidate(preferred)

    def discovery_worker(search_path: Path) -> None:
        try:
            candidates = discover_rosbags(search_path, max_depth=4, max_candidates=100)
        except (OSError, ValueError) as exc:
            root.after(0, finish_discovery, [], str(exc))
            return
        root.after(0, finish_discovery, candidates, None)

    def start_discovery(_event: object | None = None) -> None:
        search_text = source_var.get().strip()
        if not search_text:
            messagebox.showwarning("RobotDev Tools", "请选择 rosbag2 文件或待扫描目录。")
            return
        search_path = Path(search_text).expanduser()
        if not search_path.exists():
            messagebox.showerror("RobotDev Tools", f"路径不存在:\n{search_path}")
            return
        file_button.state(["disabled"])
        folder_button.state(["disabled"])
        scan_button.state(["disabled"])
        analyze_button.state(["disabled"])
        detection_var.set("正在扫描并读取 rosbag2 索引, 不反序列化消息内容…")
        discovery_progress.start(12)
        threading.Thread(target=discovery_worker, args=(search_path,), daemon=True).start()

    scan_button = ttk.Button(source_box, text="识别 / 扫描", command=start_discovery)
    scan_button.grid(row=0, column=4)
    source_entry.bind("<Return>", start_discovery)
    ttk.Label(
        source_box,
        text="目录扫描深度最多 4 层; 拆分 bag 会按同一目录合并识别, 扫描阶段不会读取消息载荷。",
        style="Subtitle.TLabel",
    ).grid(row=1, column=1, columnspan=4, sticky="w", padx=10, pady=(5, 0))

    settings_box = ttk.LabelFrame(frame, text=" 2. 门禁与报告 / Configure and analyze ", padding=14)
    settings_box.grid(row=3, column=0, sticky="ew", pady=(14, 0))
    settings_box.columnconfigure(1, weight=1)

    ttk.Label(settings_box, text="Config 门禁").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(settings_box, textvariable=config_var).grid(
        row=0, column=1, sticky="ew", padx=10, pady=5
    )

    def choose_config() -> None:
        selected = filedialog.askopenfilename(
            title="Select RobotDev YAML config",
            filetypes=[("YAML", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if selected:
            config_var.set(selected)

    ttk.Button(settings_box, text="浏览…", command=choose_config).grid(row=0, column=2)
    ttk.Label(
        settings_box,
        text="可留空; 未提供门禁时仍生成完整指标, 顶层状态为 NOT_EVALUATED。",
        style="Subtitle.TLabel",
    ).grid(row=1, column=1, columnspan=2, sticky="w", padx=10)

    ttk.Label(settings_box, text="Output 报告").grid(row=2, column=0, sticky="w", pady=(12, 5))
    ttk.Entry(settings_box, textvariable=output_var).grid(
        row=2, column=1, sticky="ew", padx=10, pady=(12, 5)
    )

    def choose_output() -> None:
        nonlocal output_user_selected
        selected = filedialog.askdirectory(title="Select report output directory")
        if selected:
            output_user_selected = True
            output_var.set(selected)

    ttk.Button(settings_box, text="浏览…", command=choose_output).grid(
        row=2, column=2, pady=(12, 5)
    )
    ttk.Checkbutton(
        settings_box,
        text="完成后在默认浏览器中打开 HTML 报告",
        variable=open_report_var,
    ).grid(row=3, column=1, columnspan=2, sticky="w", padx=10, pady=(2, 8))

    action_frame = ttk.Frame(frame)
    action_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
    action_frame.columnconfigure(0, weight=1)
    progress = ttk.Progressbar(action_frame, mode="indeterminate")
    progress.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 7))
    ttk.Label(
        action_frame,
        textvariable=status_var,
        style="Status.TLabel",
        wraplength=760,
    ).grid(row=1, column=0, sticky="w")

    def open_report() -> None:
        report = last_report["path"]
        if report is not None:
            webbrowser.open(report.resolve().as_uri())

    open_button = ttk.Button(action_frame, text="打开上次报告", command=open_report)
    open_button.grid(row=1, column=1, padx=(10, 8))
    open_button.state(["disabled"])

    def finish_success(status: str, html_path: Path, json_path: Path) -> None:
        progress.stop()
        analyze_button.state(["!disabled"])
        last_report["path"] = html_path
        open_button.state(["!disabled"])
        status_var.set(f"{status} · HTML: {html_path} · JSON: {json_path}")
        if open_report_var.get():
            open_report()

    def finish_error(message: str) -> None:
        progress.stop()
        analyze_button.state(["!disabled"])
        status_var.set(f"Analysis failed / 分析失败: {message}")
        messagebox.showerror("RobotDev Tools", message)

    def analyze_worker(selected_bag: Path, selected_config: Path | None, output: Path) -> None:
        try:
            result = analyze_bag(selected_bag, selected_config)
            html_path, json_path = write_report(result, output)
        except (AnalysisError, ConfigError, OSError, ValueError) as exc:
            root.after(0, finish_error, str(exc))
            return
        root.after(0, finish_success, result.status, html_path, json_path)

    def start_analysis() -> None:
        selected_bag_text = bag_var.get().strip()
        output_text = output_var.get().strip()
        if not selected_bag_text:
            messagebox.showwarning("RobotDev Tools", "请先扫描并选择一个可读取的 rosbag2。")
            return
        if not output_text:
            messagebox.showwarning("RobotDev Tools", "请选择报告输出目录。")
            return
        selected_bag = Path(selected_bag_text).expanduser()
        selected_config_text = config_var.get().strip()
        selected_config = Path(selected_config_text).expanduser() if selected_config_text else None
        output = Path(output_text).expanduser()
        if not selected_bag.exists():
            messagebox.showerror("RobotDev Tools", f"Bag 路径不存在:\n{selected_bag}")
            return
        if selected_config is not None and not selected_config.is_file():
            messagebox.showerror("RobotDev Tools", f"Config 文件不存在:\n{selected_config}")
            return
        analyze_button.state(["disabled"])
        open_button.state(["disabled"])
        status_var.set("Reading messages and calculating ROS diagnostics / 正在分析…")
        progress.start(12)
        threading.Thread(
            target=analyze_worker,
            args=(selected_bag, selected_config, output),
            daemon=True,
        ).start()

    analyze_button = ttk.Button(
        action_frame,
        text="开始分析并生成报告",
        command=start_analysis,
        style="Primary.TButton",
    )
    analyze_button.grid(row=1, column=2)
    analyze_button.state(["disabled"])

    ttk.Label(
        frame,
        text="隐私: 扫描、识别和分析均在本机完成, 不上传 bag; 仅向所选 Output 写入报告。",
        style="Subtitle.TLabel",
    ).grid(row=5, column=0, sticky="w", pady=(12, 0))

    if initial_source:
        root.after(150, start_discovery)
    root.mainloop()
