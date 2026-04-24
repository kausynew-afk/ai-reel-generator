import asyncio
import random
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import numpy as np


class AntiDetect:
    """Post-processing to make AI-generated video undetectable."""

    async def process(
        self,
        session_dir: str,
        grain_intensity: float = 0.02,
        audio_room_tone: bool = True,
    ) -> dict:
        session_dir = Path(session_dir)
        composed = session_dir / "composed.mp4"
        if not composed.exists():
            raise FileNotFoundError("Compose the video first before finalizing.")

        final_path = session_dir / "final_reel.mp4"

        await asyncio.to_thread(
            self._apply_video_filters,
            str(composed), str(final_path), grain_intensity
        )

        if audio_room_tone:
            await asyncio.to_thread(self._naturalize_audio, str(final_path))

        self._strip_metadata(str(final_path))

        return {
            "video_file": "final_reel.mp4",
            "filters_applied": [
                "film_grain",
                "micro_color_shift",
                "brightness_jitter",
                "lens_distortion",
                "audio_room_tone" if audio_room_tone else None,
                "metadata_stripped",
            ],
        }

    @staticmethod
    def _apply_video_filters(input_path: str, output_path: str, grain: float):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            shutil.copy2(input_path, output_path)
            return

        # Film grain + subtle brightness jitter + micro lens distortion
        noise_amount = max(1, int(grain * 500))
        brightness_var = random.uniform(-0.02, 0.02)
        hue_shift = random.uniform(-3, 3)

        vfilter = (
            f"noise=alls={noise_amount}:allf=t,"
            f"eq=brightness={brightness_var:.4f}:saturation=1.02,"
            f"hue=h={hue_shift:.1f},"
            f"unsharp=3:3:0.3:3:3:0.0,"
            f"lenscorrection=k1=-0.02:k2=0.01"
        )

        cmd = [
            ffmpeg, "-y",
            "-i", input_path,
            "-vf", vfilter,
            "-c:v", "libx264", "-preset", "medium",
            "-crf", "18",
            "-c:a", "copy",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)

    @staticmethod
    def _naturalize_audio(video_path: str):
        """Add subtle room tone and micro-compression to audio."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return

        temp_path = str(Path(video_path).with_suffix(".temp.mp4"))

        # Generate room tone noise, mix at very low volume, add subtle EQ variation
        room_vol = random.uniform(0.003, 0.008)
        afilter = (
            f"anoisesrc=d=300:c=pink:a={room_vol}[room];"
            f"[0:a][room]amix=inputs=2:duration=first:dropout_transition=0[mix];"
            f"[mix]acompressor=threshold=-25dB:ratio=2:attack=20:release=200,"
            f"equalizer=f={random.randint(2000, 4000)}:t=q:w=0.5:g={random.uniform(-1, 1):.1f}[aout]"
        )

        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-filter_complex", afilter,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            temp_path,
        ]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0 and Path(temp_path).exists():
            Path(video_path).unlink()
            Path(temp_path).rename(video_path)
        else:
            Path(temp_path).unlink(missing_ok=True)

    @staticmethod
    def _strip_metadata(video_path: str):
        """Remove all metadata and set generic camera metadata."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return

        temp_path = str(Path(video_path).with_suffix(".nometa.mp4"))

        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-map_metadata", "-1",
            "-metadata", "creation_time=",
            "-metadata", "encoder=",
            "-metadata", "comment=",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            "-c:v", "copy", "-c:a", "copy",
            temp_path,
        ]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0 and Path(temp_path).exists():
            Path(video_path).unlink()
            Path(temp_path).rename(video_path)
        else:
            Path(temp_path).unlink(missing_ok=True)
