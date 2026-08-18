"""Small local desktop interface for RobotDev Tools."""

from __future__ import annotations

import os
import platform
import threading
import webbrowser
from pathlib import Path

from robotdev_tools.analyzer import AnalysisError, analyze_bag
from robotdev_tools.config import ConfigError
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


def launch_gui(
    bag_path: Path | None = None,
    config_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Launch the local Tk desktop interface.

    Tkinter is imported lazily so terminal-only installations keep working on
    Linux machines that do not ship the optional Tk runtime.
    """

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

    root.title("RobotDev Tools")
    root.geometry("780x540")
    root.minsize(680, 500)

    default_output = output_path or Path.cwd() / "robotdev-report"
    bag_var = tk.StringVar(value=str(bag_path or ""))
    config_var = tk.StringVar(value=str(config_path or ""))
    output_var = tk.StringVar(value=str(default_output))
    open_report_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="Select a rosbag2 directory, .db3, or .mcap file.")
    last_report: dict[str, Path | None] = {"path": None}

    style = ttk.Style(root)
    if "vista" in style.theme_names() and os.name == "nt":
        style.theme_use("vista")
    title_font = tkfont.nametofont("TkDefaultFont").copy()
    title_font.configure(size=18, weight="bold")
    style.configure("Title.TLabel", font=title_font)
    style.configure("Hint.TLabel", foreground="#4b5563")
    style.configure("Status.TLabel", foreground="#1d4ed8")

    frame = ttk.Frame(root, padding=24)
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="RobotDev Tools", style="Title.TLabel").grid(
        row=0, column=0, columnspan=4, sticky="w"
    )
    ttk.Label(
        frame,
        text="本地分析 ROS 2 bag / Analyze locally — 无需 ROS，不上传数据",  # noqa: RUF001
        style="Hint.TLabel",
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 24))

    ttk.Label(frame, text="Bag 数据").grid(row=2, column=0, sticky="w", pady=7)
    ttk.Entry(frame, textvariable=bag_var).grid(row=2, column=1, sticky="ew", padx=10)

    def choose_bag_file() -> None:
        selected = filedialog.askopenfilename(
            title="Select rosbag2 file",
            filetypes=[
                ("ROS 2 bags", "*.db3 *.mcap"),
                ("SQLite3", "*.db3"),
                ("MCAP", "*.mcap"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            bag_var.set(selected)

    def choose_bag_folder() -> None:
        selected = filedialog.askdirectory(title="Select rosbag2 directory")
        if selected:
            bag_var.set(selected)

    ttk.Button(frame, text="文件…", command=choose_bag_file).grid(row=2, column=2, padx=(0, 6))
    ttk.Button(frame, text="文件夹…", command=choose_bag_folder).grid(row=2, column=3)

    ttk.Label(frame, text="Config 门禁").grid(row=3, column=0, sticky="w", pady=7)
    ttk.Entry(frame, textvariable=config_var).grid(row=3, column=1, sticky="ew", padx=10)

    def choose_config() -> None:
        selected = filedialog.askopenfilename(
            title="Select RobotDev YAML config",
            filetypes=[("YAML", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if selected:
            config_var.set(selected)

    ttk.Button(frame, text="浏览…", command=choose_config).grid(row=3, column=2, columnspan=2)
    ttk.Label(
        frame,
        text="可留空；不提供配置时只计算指标，结果为 NOT_EVALUATED。",  # noqa: RUF001
        style="Hint.TLabel",
    ).grid(row=4, column=1, columnspan=3, sticky="w", padx=10)

    ttk.Label(frame, text="Output 报告").grid(row=5, column=0, sticky="w", pady=(18, 7))
    ttk.Entry(frame, textvariable=output_var).grid(
        row=5, column=1, sticky="ew", padx=10, pady=(18, 7)
    )

    def choose_output() -> None:
        selected = filedialog.askdirectory(title="Select report output directory")
        if selected:
            output_var.set(selected)

    ttk.Button(frame, text="浏览…", command=choose_output).grid(
        row=5, column=2, columnspan=2, pady=(18, 7)
    )
    ttk.Checkbutton(
        frame,
        text="完成后在默认浏览器中打开 HTML 报告",
        variable=open_report_var,
    ).grid(row=6, column=1, columnspan=3, sticky="w", padx=10, pady=(2, 20))

    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(0, 10))
    ttk.Label(frame, textvariable=status_var, style="Status.TLabel", wraplength=700).grid(
        row=8, column=0, columnspan=4, sticky="w", pady=(0, 20)
    )

    button_frame = ttk.Frame(frame)
    button_frame.grid(row=9, column=0, columnspan=4, sticky="ew")
    button_frame.columnconfigure(0, weight=1)

    def open_report() -> None:
        report = last_report["path"]
        if report is not None:
            webbrowser.open(report.resolve().as_uri())

    open_button = ttk.Button(button_frame, text="打开上次报告", command=open_report)
    open_button.grid(row=0, column=1, padx=(0, 10))
    open_button.state(["disabled"])

    def finish_success(status: str, html_path: Path, json_path: Path) -> None:
        progress.stop()
        analyze_button.state(["!disabled"])
        last_report["path"] = html_path
        open_button.state(["!disabled"])
        status_var.set(f"{status} — HTML: {html_path} — JSON: {json_path}")
        if open_report_var.get():
            open_report()

    def finish_error(message: str) -> None:
        progress.stop()
        analyze_button.state(["!disabled"])
        status_var.set(f"Analysis failed: {message}")
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
            messagebox.showwarning("RobotDev Tools", "Select a rosbag2 file or directory first.")
            return
        if not output_text:
            messagebox.showwarning("RobotDev Tools", "Select an output directory.")
            return

        selected_bag = Path(selected_bag_text).expanduser()
        selected_config_text = config_var.get().strip()
        selected_config = Path(selected_config_text).expanduser() if selected_config_text else None
        output = Path(output_text).expanduser()
        if not selected_bag.exists():
            messagebox.showerror("RobotDev Tools", f"Bag path does not exist:\n{selected_bag}")
            return
        if selected_config is not None and not selected_config.is_file():
            messagebox.showerror(
                "RobotDev Tools", f"Config file does not exist:\n{selected_config}"
            )
            return

        analyze_button.state(["disabled"])
        open_button.state(["disabled"])
        status_var.set("Reading bag and calculating metrics…")
        progress.start(12)
        threading.Thread(
            target=analyze_worker,
            args=(selected_bag, selected_config, output),
            daemon=True,
        ).start()

    analyze_button = ttk.Button(button_frame, text="开始分析", command=start_analysis)
    analyze_button.grid(row=0, column=2)

    ttk.Separator(frame).grid(row=10, column=0, columnspan=4, sticky="ew", pady=(28, 14))
    ttk.Label(
        frame,
        text=(
            "隐私说明：分析完全在本机运行，bag 不会上传；仅在所选目录写入 "  # noqa: RUF001
            "report.html 和 summary.json。"
        ),
        style="Hint.TLabel",
        wraplength=700,
    ).grid(row=11, column=0, columnspan=4, sticky="w")

    root.mainloop()
