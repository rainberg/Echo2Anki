"""
音频标准化脚本 — 放到音频目录中直接运行

输出规范（与生产环境一致）：
- MP3 / 单声道 / 16kHz / 96kbps
- 轻度降噪 (afftdn nf=-25)
- 响度标准化 (loudnorm I=-18 TP=-2 LRA=11)

用法：
  python normalize.py                    # 处理当前目录所有音频，输出到默认目录
  python normalize.py input.mp3          # 处理单个文件
  python normalize.py -d 20260608        # 只处理文件名包含该日期的文件
  python normalize.py --no-denoise       # 不降噪
  python normalize.py -o D:\output       # 指定输出目录
"""

import subprocess
import sys
import argparse
from pathlib import Path

SUPPORTED = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus"}
DEFAULT_OUTPUT = r"J:\08_治疗优律司美\Alanus\block6"


def normalize_audio(input_path: str, output_path: str, denoise: bool = True) -> str:
    filters = []
    if denoise:
        filters.append("afftdn=nf=-25")
    filters.append("loudnorm=I=-18:TP=-2:LRA=11")

    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-af", ",".join(filters),
        "-codec:a", "libmp3lame", "-b:a", "96k",
        output_path,
    ]
    subprocess.run(command, check=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="音频标准化（与生产环境一致）")
    parser.add_argument("input", nargs="?", default=".", help="输入文件或目录（默认当前目录）")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help=f"输出目录（默认: {DEFAULT_OUTPUT}）")
    parser.add_argument("-d", "--date", default="", help="只处理文件名包含该日期的文件（如 20260608）")
    parser.add_argument("--no-denoise", action="store_true", help="跳过降噪")
    args = parser.parse_args()

    denoise = not args.no_denoise
    src = Path(args.input)
    out_dir = Path(args.output)

    if src.is_file():
        # 单文件模式
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / src.with_suffix(".mp3").name
        print(f"处理: {src.name}")
        normalize_audio(str(src), str(out_path), denoise=denoise)
        print(f"  -> {out_path}")
    else:
        # 目录模式
        in_dir = src if src.is_dir() else Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(f for f in in_dir.iterdir()
                       if f.is_file() and f.suffix.lower() in SUPPORTED
                       and (not args.date or args.date in f.name))

        if not files:
            print(f"在 {in_dir} 中未找到音频文件")
            print(f"支持格式: {', '.join(sorted(SUPPORTED))}")
            return

        print(f"找到 {len(files)} 个音频文件，输出到: {out_dir}")
        if args.date:
            print(f"日期过滤: {args.date}")
        print(f"降噪: {'开' if denoise else '关'}")
        print()

        for i, f in enumerate(files, 1):
            out_path = out_dir / f.with_suffix(".mp3").name
            print(f"[{i}/{len(files)}] {f.name}")
            try:
                normalize_audio(str(f), str(out_path), denoise=denoise)
                print(f"  -> {out_path.name}")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ 失败: {e}")

        print(f"\n完成！输出目录: {out_dir}")


if __name__ == "__main__":
    main()
