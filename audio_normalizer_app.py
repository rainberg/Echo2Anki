# -*- coding: utf-8 -*-
"""音频标准化工具 — Windows 桌面应用

将音频统一转为 MP3 / 单声道 / 16kHz(可选) / 96kbps(可选)，
轻度降噪 + 响度归一化，供 Whisper 转录或 Anki 听力卡片使用。
处理参数与服务器端 audio_normalize.py 完全一致。

- 双击运行打开图形界面，支持文件/文件夹拖拽
- 首次运行自动下载 ffmpeg 到程序目录 ffmpeg_bin\\
- 也支持命令行: AudioNormalizer.exe 文件1 [文件2 ...] [-d 输出目录]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import queue
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import concurrent.futures as cf

APP_NAME = "音频标准化工具"
APP_VERSION = "1.0"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac",
              ".wma", ".mp4", ".mkv", ".webm", ".amr", ".3gp"}
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# 拖拽支持（可选，打包时带上 tkinterdnd2）
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    _HAS_DND = False


def app_dir() -> Path:
    """程序所在目录（exe 打包后取 exe 目录，脚本运行取脚本目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def safe_print(*args, **kwargs) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        print(*args, **kwargs, flush=True)
    except Exception:
        pass


# ================================================================ ffmpeg 管理

def find_ffmpeg() -> Path | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return Path(exe).parent
    here = app_dir()
    for p in (
        here / "ffmpeg_bin" / "ffmpeg.exe",
        Path(os.environ.get("FFMPEG_PATH", "")) if os.environ.get("FFMPEG_PATH") else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Links/ffmpeg.exe",
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path(sys.prefix) / "Library/bin/ffmpeg.exe",
    ):
        if p and p.is_file():
            return p.parent
    return None


def download_ffmpeg(dest: Path, progress_cb=None) -> bool:
    """下载 ffmpeg essentials 到 dest 目录，progress_cb(percent, text)。"""
    dest.mkdir(parents=True, exist_ok=True)
    tmp_zip = Path(tempfile.gettempdir()) / "ffmpeg-release-essentials.zip"

    def hook(blocks: int, block_size: int, total: int):
        if progress_cb and total > 0:
            done = min(blocks * block_size, total)
            progress_cb(done * 100 // total, f"下载中 {done // 1048576} / {total // 1048576} MB")

    try:
        if progress_cb:
            progress_cb(0, "连接下载源…")
        urllib.request.urlretrieve(FFMPEG_URL, tmp_zip, reporthook=hook)
        if progress_cb:
            progress_cb(100, "解压中…")
        with zipfile.ZipFile(tmp_zip) as zf:
            for name in zf.namelist():
                base = os.path.basename(name)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    with zf.open(name) as src, open(dest / base, "wb") as out:
                        shutil.copyfileobj(src, out)
        tmp_zip.unlink(missing_ok=True)
    except Exception as e:
        safe_print(f"ffmpeg 下载失败: {e}")
        if progress_cb:
            progress_cb(0, f"下载失败: {e}")
        return False
    return (dest / "ffmpeg.exe").is_file()


# ================================================================ 核心转换

def normalize_one(bin_dir: Path, src: Path, out_path: Path,
                  sample_rate: int, bitrate: str, denoise: bool) -> tuple[str, str]:
    """转换单个文件，返回 (输出路径, ffprobe 描述)。与服务器参数一致。"""
    filters = []
    if denoise:
        filters.append("afftdn=nf=-25")
    filters.append("loudnorm=I=-18:TP=-2:LRA=11")

    ffmpeg = bin_dir / ("ffmpeg.exe" if (bin_dir / "ffmpeg.exe").is_file() else "ffmpeg")
    ffprobe = bin_dir / ("ffprobe.exe" if (bin_dir / "ffprobe.exe").is_file() else "ffprobe")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg), "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-af", ",".join(filters),
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffmpeg 未知错误").strip()[-400:])

    info_cmd = [str(ffprobe), "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=channels,sample_rate:format=duration",
                "-of", "default=noprint_wrappers=1", str(out_path)]
    p2 = subprocess.run(info_cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    info = " ".join(p2.stdout.split()) if p2.returncode == 0 else ""
    return str(out_path), info


def collect_inputs(paths) -> list[Path]:
    files: list[Path] = []
    for item in paths:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXTS))
        elif p.is_file():
            files.append(p)
    seen, uniq = set(), []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


# ================================================================ 配置

def config_path() -> Path:
    p = app_dir() / "audio_normalizer_config.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8"):
            pass
        return p
    except OSError:
        return Path(os.environ.get("LOCALAPPDATA", tempdir_fallback())) / "audio_normalizer_config.json"


def tempdir_fallback() -> str:
    return tempfile.gettempdir()


DEFAULT_CONFIG = {
    "sample_rate": 16000,
    "bitrate": "96k",
    "denoise": True,
    "output_mode": "same",   # same | custom
    "output_dir": "",
    "jobs": 2,
    "ui_scale": 1.0,         # 1.0 = 默认, 1.1 = 放大 10%, 0.9 = 缩小 10%
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULT_CONFIG})
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ================================================================ 命令行模式

def run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}（命令行模式）")
    parser.add_argument("inputs", nargs="+", help="音频文件或文件夹")
    parser.add_argument("-d", "--output-dir", help="输出目录（默认与源文件同目录）")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--bitrate", default="96k")
    parser.add_argument("--no-denoise", action="store_true")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args(argv)

    bin_dir = find_ffmpeg()
    if bin_dir is None:
        dest = app_dir() / "ffmpeg_bin"

        def cli_progress(pct: int, txt: str) -> None:
            safe_print(f"\r{txt}   ", end="")
            if pct >= 100:
                safe_print("")

        safe_print("未找到 ffmpeg，开始自动下载…")
        if not download_ffmpeg(dest, cli_progress):
            return 1
        bin_dir = dest
    files = collect_inputs(args.inputs)
    safe_print(f"ffmpeg: {bin_dir} | 共 {len(files)} 个文件")
    out_dir = Path(args.output_dir) if args.output_dir else None
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {f: pool.submit(normalize_one, bin_dir, f,
                               (out_dir / f"{f.stem}.normalized.mp3") if out_dir else f.with_name(f"{f.stem}.normalized.mp3"),
                               args.sample_rate, args.bitrate, not args.no_denoise)
                for f in files}
        for f, fut in futs.items():
            try:
                result, info = fut.result()
                ok += 1
                safe_print(f"[OK] {f.name} -> {Path(result).name}  {info}")
            except Exception as e:
                fail += 1
                safe_print(f"[失败] {f.name}: {e}")
    safe_print(f"完成: 成功 {ok} / 失败 {fail}")
    return 0 if fail == 0 else 2


# ================================================================ 图形界面

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.q: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.bin_dir: Path | None = None
        self.last_out_dir: str | None = None

        root.title(f"{APP_NAME} v{APP_VERSION}")

        # ---------- DPI：感知已在 run_gui() 中、创建 root 之前启用 ----------
        # 此时 winfo_fpixels 返回真实 DPI（如 250% 缩放 → 240），
        # tk scaling 换算 pt→px，字体自动跟随系统缩放
        try:
            root.update()
            dpi = float(root.winfo_fpixels("1i"))
            root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            dpi = 96.0
        self._dpi_scale = max(1.0, dpi / 96.0)   # 像素尺寸放大系数（250% → 2.5）

        # 统一字体（微软雅黑；pt 值固定，由 tk scaling 自动按系统 DPI 放大）
        ui_scale = float(self.cfg.get("ui_scale", 1.0))
        base_font_size = 11
        self._font_size_init = base_font_size          # 基准（用于滑块换算）
        scaled_font_size = max(9, min(24, round(base_font_size * ui_scale)))
        self._font_size = scaled_font_size
        self._style = ttk.Style(root)
        for family in ("vista", "clam", "default", "alt"):
            try:
                self._style.theme_use(family)
                break
            except Exception:
                continue
        self._apply_fonts(scaled_font_size)

        # 窗口尺寸也按系统缩放放大，保证高 DPI 下布局比例不变
        s = self._dpi_scale
        root.geometry(f"{int(820 * s)}x{int(620 * s)}")
        root.minsize(int(680 * s), int(520 * s))

        self._build_ui()
        self._apply_config()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(200, self._init_ffmpeg)
        self._poll_queue()

    # ---------- UI 构建 ----------
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}
        s = self._dpi_scale   # 系统缩放系数（像素尺寸按此放大）

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(top, text="添加文件夹", command=self.add_folder).pack(side="left", padx=4)
        ttk.Button(top, text="移除选中", command=self.remove_selected).pack(side="left")
        ttk.Button(top, text="清空列表", command=self.clear_list).pack(side="left", padx=4)
        if _HAS_DND:
            ttk.Label(top, text="（也可直接把文件/文件夹拖进窗口）").pack(side="right")

        columns = ("file", "status", "detail")
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        self.tree.heading("file", text="文件")
        self.tree.heading("status", text="状态")
        self.tree.heading("detail", text="详情")
        self.tree.column("file", width=int(340 * s))
        self.tree.column("status", width=int(90 * s), anchor="center")
        self.tree.column("detail", width=int(330 * s))
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        settings = ttk.LabelFrame(self.root, text="输出设置")
        settings.pack(fill="x", **pad)

        row1 = ttk.Frame(settings)
        row1.pack(fill="x", **pad)
        ttk.Label(row1, text="采样率:").pack(side="left")
        self.rate_var = tk.StringVar(value="16000")
        ttk.Combobox(row1, textvariable=self.rate_var, width=8, state="readonly",
                     values=["8000", "16000", "22050", "44100"]).pack(side="left", padx=(2, 10))
        ttk.Label(row1, text="比特率:").pack(side="left")
        self.br_var = tk.StringVar(value="96k")
        ttk.Combobox(row1, textvariable=self.br_var, width=8, state="readonly",
                     values=["64k", "96k", "128k", "192k"]).pack(side="left", padx=(2, 10))
        self.denoise_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="降噪（afftdn）", variable=self.denoise_var).pack(side="left", padx=4)
        ttk.Label(row1, text="并行数:").pack(side="left", padx=(10, 0))
        self.jobs_var = tk.StringVar(value="2")
        ttk.Combobox(row1, textvariable=self.jobs_var, width=3, state="readonly",
                     values=["1", "2", "3", "4"]).pack(side="left", padx=2)

        row2 = ttk.Frame(settings)
        row2.pack(fill="x", **pad)
        self.out_same_var = tk.BooleanVar(value=True)
        ttk.Radiobutton(row2, text="输出到源文件目录", variable=self.out_same_var,
                        value=True, command=self._toggle_outdir).pack(side="left")
        ttk.Radiobutton(row2, text="输出到:", variable=self.out_same_var,
                        value=False, command=self._toggle_outdir).pack(side="left", padx=(10, 2))
        self.outdir_var = tk.StringVar()
        self.outdir_entry = ttk.Entry(row2, textvariable=self.outdir_var, width=48)
        self.outdir_entry.pack(side="left", padx=2)
        self.outdir_btn = ttk.Button(row2, text="浏览…", command=self.choose_outdir)
        self.outdir_btn.pack(side="left")

        # 第三行：界面缩放
        row3 = ttk.Frame(settings)
        row3.pack(fill="x", **pad)
        ttk.Label(row3, text="界面缩放:").pack(side="left")
        self.scale_var = tk.DoubleVar(value=float(self.cfg.get("ui_scale", 1.0)))
        self.scale_slider = ttk.Scale(row3, from_=0.7, to=1.6, length=int(200 * s),
                                      orient="horizontal", variable=self.scale_var,
                                      command=self._on_scale_change)
        self.scale_slider.pack(side="left", padx=(2, 6))
        self.scale_label = ttk.Label(row3, text=f"{int(float(self.scale_var.get()) * 100)}%", width=6)
        self.scale_label.pack(side="left")
        ttk.Button(row3, text="重置", command=lambda: self.scale_var.set(1.0)).pack(side="left", padx=4)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.start_btn = ttk.Button(bottom, text="开始转换", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bottom, text="取消", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        self.open_btn = ttk.Button(bottom, text="打开输出目录", command=self.open_outdir, state="disabled")
        self.open_btn.pack(side="left")

        self.ff_label = ttk.Label(self.root, text="ffmpeg: 检测中…", foreground="gray")
        self.ff_label.pack(anchor="w", **pad)
        self.dl_btn = ttk.Button(self.root, text="下载 ffmpeg", command=self._start_download, state="disabled")
        self.dl_btn.pack(anchor="w", padx=6)
        self.dl_progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.dl_progress.pack(fill="x", padx=6, pady=(0, 2))

        log_frame = ttk.LabelFrame(self.root, text="日志")
        log_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text = tk.Text(log_frame, height=8, state="disabled",
                                font=("Consolas", max(9, self._font_size - 1)))
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        if _HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _apply_fonts(self, size: int):
        """把 ttk 所有控件和日志 Text 的字体统一到 size（点）；行高等像素尺寸按系统缩放放大。"""
        s = getattr(self, "_dpi_scale", 1.0)
        self._style.configure(".", font=("Microsoft YaHei UI", size))
        self._style.configure("TButton", font=("Microsoft YaHei UI", size))
        self._style.configure("TLabel", font=("Microsoft YaHei UI", size))
        self._style.configure("TCombobox", font=("Microsoft YaHei UI", size))
        self._style.configure("TEntry", font=("Microsoft YaHei UI", size))
        self._style.configure("TRadiobutton", font=("Microsoft YaHei UI", size))
        self._style.configure("TCheckbutton", font=("Microsoft YaHei UI", size))
        self._style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", size, "bold"))
        self._style.configure("Treeview", font=("Microsoft YaHei UI", size),
                               rowheight=int(size * 2.2 * s))
        self._style.configure("Treeview.Heading", font=("Microsoft YaHei UI", size, "bold"))
        self._style.configure("Horizontal.TProgressbar", thickness=int(size * 2.5 * s))
        # Text 控件单独调
        if hasattr(self, "log_text"):
            self.log_text.configure(font=("Consolas", max(9, size - 1)))

    def _on_scale_change(self, value: str):
        """拖动缩放滑块时实时调整字体。"""
        scale = float(value)
        self.scale_label.configure(text=f"{int(scale * 100)}%")
        new_size = max(9, min(20, round(self._font_size_init * scale)))
        if new_size != self._font_size:
            self._font_size = new_size
            self._apply_fonts(new_size)

    def _toggle_outdir(self):
        state = "normal" if not self.out_same_var.get() else "disabled"
        self.outdir_entry.configure(state=state)
        self.outdir_btn.configure(state=state)

    # ---------- 拖拽 / 添加文件 ----------
    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self._add_paths(paths)

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择音频文件",
            filetypes=[("音频文件", " ".join("*" + e for e in sorted(AUDIO_EXTS))),
                       ("所有文件", "*.*")])
        self._add_paths(paths)

    def add_folder(self):
        d = filedialog.askdirectory(title="选择文件夹（递归扫描音频）")
        if d:
            self._add_paths([d])

    def _add_paths(self, paths):
        added = 0
        for f in collect_inputs(paths):
            if f.suffix.lower() not in AUDIO_EXTS:
                continue
            self.tree.insert("", "end", iid=str(f), values=(f.name, "等待", ""))
            added += 1
        if added:
            self._update_progress_total()
        else:
            self.log("未发现可处理的音频文件")

    def remove_selected(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
        self._update_progress_total()

    def clear_list(self):
        self.tree.delete(*self.tree.get_children())
        self._update_progress_total()

    def _update_progress_total(self):
        total = len(self.tree.get_children())
        self.progress.configure(maximum=max(total, 1), value=0)

    # ---------- ffmpeg ----------
    def _init_ffmpeg(self):
        threading.Thread(target=self._check_ffmpeg, daemon=True).start()

    def _check_ffmpeg(self):
        self.bin_dir = find_ffmpeg()
        if self.bin_dir:
            self.q.put(("ffmpeg_ok", str(self.bin_dir)))
        else:
            self.q.put(("ffmpeg_missing", None))

    def _start_download(self):
        self.dl_btn.configure(state="disabled")
        self.dl_progress.configure(value=0)
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        dest = app_dir() / "ffmpeg_bin"
        ok = download_ffmpeg(dest, lambda pct, txt: self.q.put(("dl_progress", (pct, txt))))
        self.q.put(("ffmpeg_ok", str(dest)) if ok else ("ffmpeg_missing", None))

    # ---------- 转换 ----------
    def start(self):
        iids = list(self.tree.get_children())
        pending = [i for i in iids if self.tree.set(i, "status") in ("等待", "失败")]
        if not pending:
            messagebox.showinfo(APP_NAME, "请先添加音频文件")
            return
        if not self.bin_dir:
            messagebox.showwarning(APP_NAME, "ffmpeg 尚未就绪，请先下载")
            return

        self._save_cfg_from_ui()
        out_dir = None if self.out_same_var.get() else Path(self.outdir_var.get())
        if out_dir is not None and not out_dir.is_dir():
            messagebox.showwarning(APP_NAME, f"输出目录不存在:\n{out_dir}")
            return

        self.cancel_event.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self._update_progress_total()
        self.log(f"—— 开始转换 {len(pending)} 个文件 "
                 f"(采样率 {self.rate_var.get()}Hz / {self.br_var.get()} / "
                 f"降噪={'开' if self.denoise_var.get() else '关'}) ——")

        src_map = {i: Path(i) for i in pending}
        self.worker = threading.Thread(
            target=self._convert_worker,
            args=(self.bin_dir, src_map, out_dir,
                  int(self.rate_var.get()), self.br_var.get(),
                  self.denoise_var.get(), int(self.jobs_var.get())),
            daemon=True)
        self.worker.start()

    def _convert_worker(self, bin_dir, src_map, out_dir, rate, br, denoise, jobs):
        """主转换线程：动态派发任务，取消后不再提交新任务。"""
        items = iter(src_map.items())

        def next_task(pool):
            nxt = next(items, None)
            if not nxt:
                return None
            iid, src = nxt
            dest = (out_dir / f"{src.stem}.normalized.mp3") if out_dir else src.with_name(f"{src.stem}.normalized.mp3")
            return pool.submit(normalize_one, bin_dir, src, dest, rate, br, denoise), iid, dest

        done_count = 0
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            inflight = {}
            for _ in range(max(1, jobs)):
                t = next_task(pool)
                if t:
                    fut, iid, dest = t
                    inflight[fut] = (iid, dest)
            while inflight:
                finished, _ = cf.wait(inflight, return_when=cf.FIRST_COMPLETED)
                for fut in finished:
                    iid, dest = inflight.pop(fut)
                    done_count += 1
                    try:
                        result, info = fut.result()
                        self.q.put(("done", (iid, str(dest), info)))
                    except Exception as e:
                        self.q.put(("fail", (iid, str(e))))
                    self.q.put(("progress", done_count))
                if self.cancel_event.is_set():
                    continue
                for _ in range(len(finished)):
                    t = next_task(pool)
                    if t:
                        fut, iid, dest = t
                        inflight[fut] = (iid, dest)
        self.q.put(("all_done", None))

    def cancel(self):
        self.cancel_event.set()
        self.log("已请求取消（当前文件会继续处理完）")
        self.cancel_btn.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "done":
                    iid, result, info = payload
                    self.tree.set(iid, "status", "完成")
                    self.tree.set(iid, "detail", f"{Path(result).name}  {info}")
                    self.last_out_dir = str(Path(result).parent)
                    self.open_btn.configure(state="normal")
                elif kind == "fail":
                    iid, err = payload
                    self.tree.set(iid, "status", "失败")
                    self.tree.set(iid, "detail", err[:120])
                elif kind == "progress":
                    self.progress.step(1)
                elif kind == "ffmpeg_ok" and payload:
                    self.bin_dir = Path(payload)
                    self.ff_label.configure(text=f"ffmpeg: {self.bin_dir}", foreground="green")
                    self.dl_btn.configure(state="disabled")
                    self.dl_progress.configure(value=0)
                elif kind == "ffmpeg_missing":
                    self.ff_label.configure(text="ffmpeg: 未找到 — 点击下方「下载 ffmpeg」自动获取", foreground="red")
                    self.dl_btn.configure(state="normal")
                elif kind == "dl_progress":
                    pct, txt = payload
                    self.dl_progress.configure(value=pct)
                    self.ff_label.configure(text=f"ffmpeg: {txt}", foreground="orange")
                elif kind == "all_done":
                    self.start_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    statuses = [self.tree.set(i, "status") for i in self.tree.get_children()]
                    self.log(f"—— 全部结束: 成功 {statuses.count('完成')} / 失败 {statuses.count('失败')} ——")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    # ---------- 其它 ----------
    def choose_outdir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.outdir_var.set(d)
            self.out_same_var.set(False)
            self._toggle_outdir()

    def open_outdir(self):
        if self.last_out_dir and Path(self.last_out_dir).is_dir():
            os.startfile(self.last_out_dir)  # noqa: S606

    def _apply_config(self):
        c = self.cfg
        self.rate_var.set(str(c["sample_rate"]))
        self.br_var.set(c["bitrate"])
        self.denoise_var.set(bool(c["denoise"]))
        self.jobs_var.set(str(c["jobs"]))
        if c["output_mode"] == "custom" and c["output_dir"]:
            self.out_same_var.set(False)
            self.outdir_var.set(c["output_dir"])
        self._toggle_outdir()

    def _save_cfg_from_ui(self):
        self.cfg.update({
            "sample_rate": int(self.rate_var.get()),
            "bitrate": self.br_var.get(),
            "denoise": self.denoise_var.get(),
            "output_mode": "same" if self.out_same_var.get() else "custom",
            "output_dir": self.outdir_var.get(),
            "jobs": int(self.jobs_var.get()),
            "ui_scale": round(float(self.scale_var.get()), 2),
        })
        save_config(self.cfg)

    def _on_close(self):
        self._save_cfg_from_ui()
        self.cancel_event.set()
        self.root.destroy()

    def log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def _enable_dpi_awareness() -> None:
    """必须在创建 Tk() 之前调用：Tk 创建窗口那一刻读取 DPI，
    之后设置感知无效。启用后字体/布局自动跟随系统缩放（如 250%）。"""
    try:
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(2)   # Per-Monitor V2（Win10 1703+）
        except Exception:
            try:
                windll.shcore.SetProcessDpiAwareness(1)  # System DPI 感知
            except Exception:
                windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def run_gui() -> int:
    _enable_dpi_awareness()
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    App(root)
    root.mainloop()
    return 0


def main() -> int:
    try:
        # 拖拽到 exe 上 → argv 是文件路径；直接双击 → 无 argv 打开 GUI
        if len(sys.argv) > 1:
            return run_cli(sys.argv[1:])
        return run_gui()
    except Exception:
        import traceback
        try:
            with open(app_dir() / "audio_normalizer_error.log", "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main())
