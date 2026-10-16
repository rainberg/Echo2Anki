# -*- coding: utf-8 -*-
"""Windows 本地音频标准化工具（为 Whisper 转录预处理，与服务器 audio_normalize.py 参数一致）

输出规格：MP3 / 单声道 / 16 kHz / 96 kbps / 轻度降噪(可选) / 响度归一化(loudnorm I=-18)

用法:
  1) 拖拽: 把音频文件(或文件夹)拖到 normalize_audio_win.bat 上
  2) 命令行:
     python normalize_audio_win.py 输入1.mp3 输入2.m4a [更多文件或文件夹...]
     python normalize_audio_win.py -i 某音频.wav -o 输出.mp3 --bitrate 128k --no-denoise
  3) 无参数双击/运行: 弹出文件选择窗口

首次运行若找不到 ffmpeg，会提示自动下载（放到脚本目录 ffmpeg_bin\\ 下）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma", ".mp4", ".mkv", ".webm", ".amr", ".3gp"}
FFMPEG_DIR = Path(__file__).resolve().parent / "ffmpeg_bin"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def log(msg: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(msg, flush=True)


# ---------------------------------------------------------------- ffmpeg 定位

def find_ffmpeg(explicit: str | None = None) -> Path | None:
    """按优先级查找 ffmpeg.exe，返回所在目录。"""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("FFMPEG_PATH")
    if env:
        candidates.append(Path(env))
    exe = shutil.which("ffmpeg")
    if exe:
        return Path(exe).parent
    candidates.append(FFMPEG_DIR / "ffmpeg.exe")
    # 常见安装位置
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (
        Path(local) / "Microsoft/WinGet/Links/ffmpeg.exe",
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path(sys.prefix) / "Library/bin/ffmpeg.exe",  # conda 环境
    ):
        candidates.append(p)
    for c in candidates:
        if c.is_file():
            return c.parent
    return None


def download_ffmpeg() -> bool:
    """下载并解压 ffmpeg 到脚本目录 ffmpeg_bin\\ 下。"""
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    log(f"正在下载 ffmpeg（约 80MB，仅首次）...\n  {FFMPEG_URL}")
    tmp_zip = Path(tempfile.gettempdir()) / "ffmpeg-release-essentials.zip"
    try:
        urllib.request.urlretrieve(FFMPEG_URL, tmp_zip)
        with zipfile.ZipFile(tmp_zip) as zf:
            for name in zf.namelist():
                base = os.path.basename(name)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    with zf.open(name) as src, open(FFMPEG_DIR / base, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        tmp_zip.unlink(missing_ok=True)
    except Exception as e:
        log(f"下载失败: {e}\n请手动安装 ffmpeg（winget install Gyan.FFmpeg）后重试。")
        return False
    return (FFMPEG_DIR / "ffmpeg.exe").is_file()


def ensure_ffmpeg(explicit: str | None) -> Path:
    bin_dir = find_ffmpeg(explicit)
    if bin_dir is None:
        ans = "y"
        if sys.stdin is not None and sys.stdin.isatty():
            try:
                ans = input("未找到 ffmpeg。是否自动下载到 ffmpeg_bin\\？[Y/n] ").strip().lower()
            except EOFError:
                ans = "y"
        if ans in ("", "y", "yes"):
            if download_ffmpeg():
                return FFMPEG_DIR
        log("未找到 ffmpeg，退出。安装后重跑本程序即可。")
        sys.exit(1)
    return bin_dir


# ---------------------------------------------------------------- 核心处理

def normalize_one(bin_dir: Path, src: Path, out_path: Path, sample_rate: int, bitrate: str, denoise: bool) -> str:
    filters = []
    if denoise:
        filters.append("afftdn=nf=-25")  # 与服务器一致的保守降噪，避免损伤辅音
    filters.append("loudnorm=I=-18:TP=-2:LRA=11")

    cmd = [
        str(bin_dir / "ffmpeg.exe" if (bin_dir / "ffmpeg.exe").is_file() else bin_dir / "ffmpeg"),
        "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-af", ",".join(filters),
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffmpeg 未知错误").strip()[-500:])
    return str(out_path)


def describe(bin_dir: Path, path: Path) -> str:
    cmd = [
        str(bin_dir / "ffprobe.exe" if (bin_dir / "ffprobe.exe").is_file() else bin_dir / "ffprobe"),
        "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=channels,sample_rate:format=duration",
        "-of", "default=noprint_wrappers=1", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return " ".join(proc.stdout.split()) if proc.returncode == 0 else ""


def collect_inputs(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXTS))
        elif p.is_file():
            files.append(p)
        else:
            log(f"[跳过] 不存在: {p}")
    # 去重保序
    seen, uniq = set(), []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows 音频标准化（MP3/mono/16kHz/96k + loudnorm），供 Whisper 转录用")
    parser.add_argument("inputs", nargs="*", help="音频文件或文件夹（可多个，支持拖拽传入）")
    parser.add_argument("-i", "--input", help="单个输入文件（与 inputs 二选一）")
    parser.add_argument("-o", "--output", help="输出路径（仅 --input 单文件时有效，默认 <原名>.normalized.mp3）")
    parser.add_argument("-d", "--output-dir", help="批量输出目录（默认与源文件同目录）")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--bitrate", default="96k")
    parser.add_argument("--no-denoise", action="store_true", help="关闭降噪（默认开启 afftdn）")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="并行数")
    parser.add_argument("--ffmpeg", help="手动指定 ffmpeg 路径或其所在目录")
    args = parser.parse_args()

    sources = collect_inputs([args.input] if args.input else args.inputs)
    if not sources:
        # 无参数 → 弹出文件选择窗口
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            paths = filedialog.askopenfilenames(title="选择要标准化的音频文件（可多选）")
            root.destroy()
            sources = collect_inputs(list(paths))
        except Exception:
            pass
        if not sources:
            parser.print_help()
            sys.exit(1)

    bin_dir = ensure_ffmpeg(args.ffmpeg)
    log(f"ffmpeg: {bin_dir}")
    log(f"共 {len(sources)} 个文件 | 输出: MP3 mono {args.sample_rate}Hz {args.bitrate} 降噪={'关' if args.no_denoise else '开'}\n")

    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {}
        for src in sources:
            if args.output and len(sources) == 1:
                dest = Path(args.output)
            elif out_dir:
                dest = out_dir / f"{src.stem}.normalized.mp3"
            else:
                dest = src.with_name(f"{src.stem}.normalized.mp3")
            futures[pool.submit(normalize_one, bin_dir, src, dest, args.sample_rate, args.bitrate, not args.no_denoise)] = (src, dest)

        for fut in as_completed(futures):
            src, dest = futures[fut]
            try:
                result = fut.result()
                info = describe(bin_dir, Path(result))
                ok += 1
                log(f"[OK] {src.name} -> {Path(result).name}   {info}")
            except Exception as e:
                fail += 1
                log(f"[失败] {src.name}: {e}")

    log(f"\n完成: 成功 {ok} / 失败 {fail}")
    sys.exit(0 if fail == 0 else 2)


if __name__ == "__main__":
    main()
