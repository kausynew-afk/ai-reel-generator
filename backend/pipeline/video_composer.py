import asyncio
import json
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CANVAS_W, CANVAS_H = 1080, 1920
FPS = 24


class VideoComposer:
    async def compose(
        self,
        session_dir: str,
        add_captions: bool = True,
        caption_style: str = "word_highlight",
    ) -> dict:
        session_dir = Path(session_dir)
        avatar_video = session_dir / "avatar_video.mp4"
        voiceover = session_dir / "voiceover.mp3"
        bgm_file = self._find_bgm(session_dir)
        subs_file = session_dir / "subtitles.json"

        if not avatar_video.exists():
            raise FileNotFoundError("Avatar video not found. Generate avatar first.")
        if not voiceover.exists():
            raise FileNotFoundError("Voiceover not found. Generate voice first.")

        subtitles = []
        if subs_file.exists() and add_captions:
            with open(subs_file, "r", encoding="utf-8") as f:
                subtitles = json.load(f)

        composed_path = session_dir / "composed.mp4"

        await asyncio.to_thread(
            self._compose_with_ffmpeg,
            avatar_video=str(avatar_video),
            voiceover=str(voiceover),
            bgm=str(bgm_file) if bgm_file else None,
            subtitles=subtitles,
            caption_style=caption_style,
            output_path=str(composed_path),
            session_dir=str(session_dir),
        )

        return {
            "video_file": "composed.mp4",
            "has_captions": add_captions and len(subtitles) > 0,
            "has_bgm": bgm_file is not None,
        }

    @staticmethod
    def _find_bgm(session_dir: Path) -> Optional[Path]:
        for ext in (".mp3", ".wav", ".ogg"):
            p = session_dir / f"bgm{ext}"
            if p.exists():
                return p
        return None

    @staticmethod
    def _compose_with_ffmpeg(
        avatar_video: str,
        voiceover: str,
        bgm: Optional[str],
        subtitles: list,
        caption_style: str,
        output_path: str,
        session_dir: str,
    ):
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found.")

        srt_path = None
        if subtitles:
            srt_path = str(Path(session_dir) / "captions.srt")
            _generate_srt(subtitles, srt_path, caption_style)

        filter_parts = []
        inputs = ["-i", avatar_video, "-i", voiceover]
        audio_map = "[1:a]"

        if bgm:
            inputs.extend(["-i", bgm])
            bgm_idx = 2
            filter_parts.append(
                f"[{bgm_idx}:a]volume=0.12[bgm];"
                f"[1:a][bgm]amix=inputs=2:duration=shortest:dropout_transition=2[mixed]"
            )
            audio_map = "[mixed]"

        if srt_path:
            srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
            if bgm:
                filter_parts[-1] = filter_parts[-1].rstrip(";") + ";"
            filter_parts.append(
                f"[0:v]subtitles='{srt_escaped}':force_style="
                f"'FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,Outline=2,Shadow=1,"
                f"Alignment=2,MarginV=180'[vout]"
            )
            video_map = "[vout]"
        else:
            video_map = "0:v"

        cmd = [ffmpeg, "-y"] + inputs

        if filter_parts:
            full_filter = "".join(filter_parts)
            cmd.extend(["-filter_complex", full_filter])
            cmd.extend(["-map", video_map, "-map", audio_map])
        else:
            cmd.extend(["-map", "0:v", "-map", "1:a"])

        cmd.extend([
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ])

        subprocess.run(cmd, check=True, capture_output=True)


def _generate_srt(subtitles: list, output_path: str, style: str):
    """Convert word timestamps to SRT subtitle format."""
    lines = []
    idx = 1

    if style == "word_highlight":
        chunk_size = 4
        i = 0
        while i < len(subtitles):
            chunk = subtitles[i : i + chunk_size]
            start_ms = chunk[0]["offset_ms"]
            last = chunk[-1]
            end_ms = last["offset_ms"] + last["duration_ms"]

            text = " ".join(w["text"] for w in chunk)
            lines.append(f"{idx}")
            lines.append(f"{_ms_to_srt(start_ms)} --> {_ms_to_srt(end_ms)}")
            lines.append(text)
            lines.append("")
            idx += 1
            i += chunk_size
    else:
        for word in subtitles:
            start_ms = word["offset_ms"]
            end_ms = start_ms + word["duration_ms"]
            lines.append(f"{idx}")
            lines.append(f"{_ms_to_srt(start_ms)} --> {_ms_to_srt(end_ms)}")
            lines.append(word["text"])
            lines.append("")
            idx += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _ms_to_srt(ms: int) -> str:
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
