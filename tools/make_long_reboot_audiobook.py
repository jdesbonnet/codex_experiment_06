#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate MP3 audiobook chapters for The Long Reboot using local ffmpeg flite."
    )
    parser.add_argument(
        "--source-dir",
        default="docs/the_long_reboot",
        help="Directory containing chapter_*.md files",
    )
    parser.add_argument(
        "--output-dir",
        default="results/the_long_reboot_audiobook",
        help="Directory for generated MP3 files",
    )
    parser.add_argument(
        "--voice",
        default="slt",
        help="ffmpeg flite voice (for example: slt, kal, kal16, awb, rms)",
    )
    parser.add_argument(
        "--quality",
        default="4",
        help="libmp3lame VBR quality value passed as -q:a (lower is higher quality)",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        default=[],
        help="Restrict generation to specific chapter numbers, e.g. 1 or 01. Repeatable.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing MP3 files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress details",
    )
    return parser.parse_args()


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "chapter"


def normalize_markdown(markdown: str) -> str:
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("#"):
            line = re.sub(r"^#+\s*", "", line)
        elif re.match(r"^\s*[-*]\s+", line):
            line = re.sub(r"^\s*[-*]\s+", "", line)
        elif re.match(r"^\s*\d+\.\s+", line):
            line = re.sub(r"^\s*\d+\.\s+", "", line)

        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = line.replace("—", ", ")
        line = line.replace("–", " to ")
        line = line.replace("&", "and")
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
        else:
            lines.append("")

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + "\n"


def chapter_number_from_path(path: Path) -> str:
    match = re.search(r"chapter_(\d+)\.md$", path.name)
    if not match:
        raise ValueError(f"unexpected chapter filename: {path.name}")
    return match.group(1)


def ffprobe_duration_seconds(path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except Exception:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def main() -> int:
    args = parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return fail("ffmpeg not found")

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        return fail(f"source directory not found: {source_dir}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = {f"{int(item):02d}" for item in args.chapter} if args.chapter else None
    chapter_paths = sorted(source_dir.glob("chapter_*.md"))
    if selected is not None:
        chapter_paths = [p for p in chapter_paths if chapter_number_from_path(p) in selected]

    if not chapter_paths:
        return fail("no chapter markdown files found")

    manifest: list[dict[str, object]] = []
    playlist_lines: list[str] = ["#EXTM3U"]

    with tempfile.TemporaryDirectory(prefix="long_reboot_audio_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        for chapter_path in chapter_paths:
            chapter_no = chapter_number_from_path(chapter_path)
            markdown = chapter_path.read_text(encoding="utf-8")
            title_match = re.search(r"^#\s+(.+)$", markdown, re.M)
            title = title_match.group(1).strip() if title_match else chapter_path.stem
            plain_text = normalize_markdown(markdown)

            txt_path = temp_dir / f"{chapter_no}.txt"
            txt_path.write_text(plain_text, encoding="utf-8")

            output_name = f"{chapter_no}_{slugify(title)}.mp3"
            output_path = output_dir / output_name

            if output_path.exists() and not args.force:
                if args.verbose:
                    print(f"skip existing {output_path}")
                duration = ffprobe_duration_seconds(output_path)
            else:
                if args.verbose:
                    print(f"generate {output_path}")
                filter_spec = f"flite=textfile={txt_path}:voice={args.voice}"
                cmd = [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    filter_spec,
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    str(args.quality),
                    str(output_path),
                ]
                try:
                    subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError:
                    return fail(f"ffmpeg generation failed for {chapter_path}")
                duration = ffprobe_duration_seconds(output_path)

            manifest.append(
                {
                    "chapter_number": int(chapter_no),
                    "title": title,
                    "source_markdown": str(chapter_path),
                    "output_mp3": str(output_path),
                    "duration_seconds": duration,
                    "voice": args.voice,
                }
            )
            if duration is not None:
                playlist_lines.append(f"#EXTINF:{int(round(duration))},{title}")
            playlist_lines.append(output_name)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    playlist_path = output_dir / "playlist.m3u"
    playlist_path.write_text("\n".join(playlist_lines) + "\n", encoding="utf-8")

    print(f"generated {len(chapter_paths)} chapter mp3 files in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
