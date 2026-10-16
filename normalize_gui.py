"""
音频标准化工具 — GUI 版本（独立 EXE，内嵌 ffmpeg）

输出规范（与生产环境一致）：
- MP3 / 单声道 / 16kHz / 96kbps
- 轻度降噪 (afftdn nf=-25)
- 响度标准化 (loudnorm I=-18 TP=-2 LRA=11)
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
from pathlib import Path

SUPPORTED = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus"}
DEFAULT_OUTPUT = r"J:\08_治疗优律司美\Alanus\block6"


def get_ffmpeg_path() -> str:
    """获取 ffmpeg 路径：优先使用同目录下的 ffmpeg.exe，否则使用系统 PATH 中的 ffmpeg"""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir 模式：EXE 在 dist/音频标准化工具/ 下
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    # 检查 EXE 同目录
    local_ffmpeg = os.path.join(base, "ffmpeg.exe")
    if os.path.isfile(local_ffmpeg):
        return local_ffmpeg

    # PyInstaller onedir: 也检查 _internal 目录
    internal_ffmpeg = os.path.join(base, "_internal", "ffmpeg.exe")
    if os.path.isfile(internal_ffmpeg):
        return internal_ffmpeg

    # 回退到系统 PATH
    return "ffmpeg"


def normalize_audio(input_path: str, output_path: str, denoise: bool = True) -> str:
    filters = []
    if denoise:
        filters.append("afftdn=nf=-25")
    filters.append("loudnorm=I=-18:TP=-2:LRA=11")

    command = [
        get_ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-af", ",".join(filters),
        "-codec:a", "libmp3lame", "-b:a", "96k",
        output_path,
    ]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run(command, check=True, **kwargs)
    return output_path


def find_audio_files(in_dir: str, date_filter: str = "") -> list:
    """递归扫描目录及子目录中的音频文件"""
    in_path = Path(in_dir)
    files = []
    for f in in_path.rglob("*"):
        if f.is_file() and f.suffix.lower() in SUPPORTED:
            if not date_filter or date_filter in f.name:
                files.append(f)
    files.sort()
    return files


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("音频标准化工具")
        self.geometry("720x560")
        self.resizable(True, True)

        self._running = False
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # ── 输入目录 ──
        frm_input = ttk.LabelFrame(self, text="输入目录（含子目录）")
        frm_input.pack(fill="x", **pad)

        self.var_input = tk.StringVar()
        ttk.Entry(frm_input, textvariable=self.var_input).pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(frm_input, text="浏览…", command=self._browse_input).pack(side="right", padx=4, pady=4)

        # ── 输出目录 ──
        frm_output = ttk.LabelFrame(self, text="输出目录")
        frm_output.pack(fill="x", **pad)

        self.var_output = tk.StringVar(value=DEFAULT_OUTPUT)
        ttk.Entry(frm_output, textvariable=self.var_output).pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(frm_output, text="浏览…", command=self._browse_output).pack(side="right", padx=4, pady=4)

        # ── 选项 ──
        frm_opts = ttk.Frame(self)
        frm_opts.pack(fill="x", **pad)

        ttk.Label(frm_opts, text="日期过滤:").pack(side="left", padx=4)
        self.var_date = tk.StringVar()
        ttk.Entry(frm_opts, textvariable=self.var_date, width=12).pack(side="left", padx=4)
        ttk.Label(frm_opts, text="(如 20260608，留空处理全部)", foreground="gray").pack(side="left", padx=4)

        self.var_denoise = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm_opts, text="启用降噪", variable=self.var_denoise).pack(side="right", padx=8)

        # ── 进度 ──
        frm_prog = ttk.Frame(self)
        frm_prog.pack(fill="x", **pad)

        self.progress = ttk.Progressbar(frm_prog, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=4)
        self.lbl_status = ttk.Label(frm_prog, text="就绪", width=20, anchor="e")
        self.lbl_status.pack(side="right", padx=4)

        # ── 按钮 ──
        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", **pad)

        self.btn_start = ttk.Button(frm_btn, text="▶ 开始", command=self._start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(frm_btn, text="■ 停止", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        # ── 文件预览 ──
        frm_preview = ttk.Frame(self)
        frm_preview.pack(fill="x", **pad)
        self.lbl_preview = ttk.Label(frm_preview, text="", foreground="gray")
        self.lbl_preview.pack(side="left", padx=4)

        # ── 日志 ──
        frm_log = ttk.LabelFrame(self, text="处理日志")
        frm_log.pack(fill="both", expand=True, **pad)

        self.log = scrolledtext.ScrolledText(frm_log, height=10, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def _browse_input(self):
        p = filedialog.askdirectory(title="选择输入目录")
        if p:
            self.var_input.set(p)
            self._update_preview(p)

    def _update_preview(self, in_dir: str):
        """选择目录后立即预览找到的音频文件数量"""
        if not in_dir or not Path(in_dir).is_dir():
            self.lbl_preview.configure(text="")
            return
        date_filter = self.var_date.get().strip()
        files = find_audio_files(in_dir, date_filter)
        if files:
            exts = {}
            for f in files:
                ext = f.suffix.lower()
                exts[ext] = exts.get(ext, 0) + 1
            detail = ", ".join(f"{ext}: {cnt}" for ext, cnt in sorted(exts.items()))
            self.lbl_preview.configure(text=f"找到 {len(files)} 个音频文件（{detail}）")
        else:
            self.lbl_preview.configure(text="未找到音频文件", foreground="red")

    def _browse_output(self):
        p = filedialog.askdirectory(title="选择输出目录")
        if p:
            self.var_output.set(p)

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        in_dir = self.var_input.get().strip()
        out_dir = self.var_output.get().strip()
        if not in_dir:
            self._log("请选择输入目录！")
            return
        if not out_dir:
            self._log("请选择输出目录！")
            return
        if not Path(in_dir).is_dir():
            self._log(f"输入目录不存在: {in_dir}")
            return

        self._running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress["value"] = 0

        threading.Thread(target=self._run, args=(in_dir, out_dir), daemon=True).start()

    def _stop(self):
        self._running = False
        self._log("正在停止…")

    def _run(self, in_dir: str, out_dir: str):
        date_filter = self.var_date.get().strip()
        denoise = self.var_denoise.get()

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 递归扫描
        files = find_audio_files(in_dir, date_filter)

        if not files:
            self.after(0, lambda: self._log(f"在 {in_dir} 及子目录中未找到音频文件"))
            self.after(0, self._done)
            return

        total = len(files)
        self.after(0, lambda: self._log(f"找到 {total} 个音频文件（含子目录）"))
        self.after(0, lambda: self._log(f"降噪: {'开' if denoise else '关'}"))
        if date_filter:
            self.after(0, lambda: self._log(f"日期过滤: {date_filter}"))
        self.after(0, lambda: self._log(""))

        success = 0
        fail = 0

        for i, f in enumerate(files, 1):
            if not self._running:
                self.after(0, lambda: self._log("已停止"))
                break

            dest = out_path / f.with_suffix(".mp3").name
            # 如果不同子目录有同名文件，加序号避免覆盖
            if dest.exists() and dest != f:
                stem = f.stem
                n = 1
                while dest.exists():
                    dest = out_path / f"{stem}_{n}.mp3"
                    n += 1

            rel_path = f.relative_to(in_dir) if len(Path(in_dir).parts) < len(f.parts) else f.name
            self.after(0, lambda i=i, n=str(rel_path): self._log(f"[{i}/{total}] {n}"))

            try:
                normalize_audio(str(f), str(dest), denoise=denoise)
                self.after(0, lambda d=dest.name: self._log(f"  -> {d}"))
                success += 1
            except subprocess.CalledProcessError as e:
                self.after(0, lambda: self._log(f"  ✗ 失败: {e}"))
                fail += 1
            except FileNotFoundError:
                self.after(0, lambda: self._log("  ✗ 找不到 ffmpeg！请将 ffmpeg.exe 放到本程序同目录下"))
                fail += 1
                break

            pct = i / total * 100
            self.after(0, lambda p=pct, i=i, t=total: self._update_progress(p, i, t))

        self.after(0, lambda: self._log(f"\n完成！成功 {success}，失败 {fail}，输出: {out_path}"))
        self.after(0, self._done)

    def _update_progress(self, pct: float, done: int, total: int):
        self.progress["value"] = pct
        self.lbl_status.configure(text=f"{done}/{total}")

    def _done(self):
        self._running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
