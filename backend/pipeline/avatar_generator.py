import asyncio
import json
import math
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List

import numpy as np
from PIL import Image, ImageDraw


CANVAS_W, CANVAS_H = 1080, 1920  # 9:16 vertical reel


class AvatarGenerator:
    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        self.avatars_dir = self.assets_dir / "avatars"
        self._ensure_default_avatars()

    # ── Public API ──

    async def generate(
        self,
        mode: str,
        audio_path: str,
        output_dir: str,
        image_path: Optional[str] = None,
        preset: str = "default",
    ) -> dict:
        output_dir = Path(output_dir)
        if mode == "animated":
            return await self._generate_animated(audio_path, output_dir, preset)
        elif mode == "realistic":
            return await self._generate_sadtalker(audio_path, output_dir, image_path, preset)
        elif mode == "lipsync":
            return await self._generate_wav2lip(audio_path, output_dir, image_path, preset)
        else:
            raise ValueError(f"Unknown avatar mode: {mode}")

    def list_presets(self) -> List[dict]:
        presets = []
        for img in self.avatars_dir.iterdir():
            if img.suffix.lower() in (".png", ".jpg", ".jpeg"):
                presets.append({
                    "name": img.stem,
                    "filename": img.name,
                    "path": f"/output/presets/{img.name}",
                })
        return presets

    # ── Mode 1: Animated Character ──

    async def _generate_animated(
        self, audio_path: str, output_dir: Path, preset: str
    ) -> dict:
        subs_path = output_dir / "subtitles.json"
        subtitles = []
        if subs_path.exists():
            with open(subs_path, "r", encoding="utf-8") as f:
                subtitles = json.load(f)

        audio_duration = await self._get_audio_duration(audio_path)
        fps = 24
        total_frames = int(audio_duration * fps)

        frames_dir = output_dir / "avatar_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        frames_dir.mkdir()

        avatar_img = self._load_avatar_image(preset)

        mouth_timeline = self._build_mouth_timeline(subtitles, audio_duration, fps)

        frame_tasks = []
        for frame_idx in range(total_frames):
            frame_tasks.append(
                asyncio.to_thread(
                    self._render_animated_frame,
                    avatar_img, frame_idx, fps, mouth_timeline,
                    frames_dir, audio_duration
                )
            )

        batch_size = 50
        for i in range(0, len(frame_tasks), batch_size):
            await asyncio.gather(*frame_tasks[i : i + batch_size])

        video_path = output_dir / "avatar_video.mp4"
        await self._frames_to_video(frames_dir, audio_path, video_path, fps)

        return {
            "video_file": "avatar_video.mp4",
            "mode": "animated",
            "frames_generated": total_frames,
            "duration_sec": round(audio_duration, 2),
        }

    def _render_animated_frame(
        self,
        avatar_base: Image.Image,
        frame_idx: int,
        fps: int,
        mouth_timeline: list,
        frames_dir: Path,
        duration: float,
    ):
        t = frame_idx / fps
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), (25, 25, 35))
        draw = ImageDraw.Draw(img)

        bob_y = int(math.sin(t * 1.5) * 8)
        sway_x = int(math.sin(t * 0.7) * 5)

        av = avatar_base.copy()
        av_w, av_h = av.size
        x = (CANVAS_W - av_w) // 2 + sway_x
        y = (CANVAS_H - av_h) // 2 - 200 + bob_y
        img.paste(av, (x, y), av if av.mode == "RGBA" else None)

        mouth_open = mouth_timeline[frame_idx] if frame_idx < len(mouth_timeline) else 0.0
        mouth_cx = CANVAS_W // 2 + sway_x
        mouth_cy = y + int(av_h * 0.72) + bob_y
        mouth_w = int(av_w * 0.18)
        mouth_h = max(3, int(mouth_open * av_w * 0.12))
        draw.ellipse(
            [mouth_cx - mouth_w, mouth_cy - mouth_h,
             mouth_cx + mouth_w, mouth_cy + mouth_h],
            fill=(180, 60, 60),
        )

        blink = (frame_idx % (fps * 3)) < 3
        eye_y = y + int(av_h * 0.38) + bob_y
        for ex in [mouth_cx - int(av_w * 0.15), mouth_cx + int(av_w * 0.15)]:
            if blink:
                draw.line([(ex - 12, eye_y), (ex + 12, eye_y)], fill=(40, 40, 50), width=3)
            else:
                draw.ellipse([ex - 12, eye_y - 10, ex + 12, eye_y + 10], fill=(240, 240, 240))
                draw.ellipse([ex - 5, eye_y - 5, ex + 5, eye_y + 5], fill=(30, 30, 40))

        frame_path = frames_dir / f"frame_{frame_idx:06d}.png"
        img.save(frame_path, "PNG")

    def _build_mouth_timeline(self, subtitles: list, duration: float, fps: int) -> list:
        total_frames = int(duration * fps)
        timeline = [0.0] * total_frames

        for word_info in subtitles:
            start_ms = word_info.get("offset_ms", 0)
            dur_ms = word_info.get("duration_ms", 200)
            start_frame = int((start_ms / 1000.0) * fps)
            end_frame = int(((start_ms + dur_ms) / 1000.0) * fps)
            for f in range(max(0, start_frame), min(total_frames, end_frame)):
                progress = (f - start_frame) / max(1, end_frame - start_frame)
                timeline[f] = math.sin(progress * math.pi) * (0.5 + 0.5 * np.random.random())

        return timeline

    # ── Mode 2: SadTalker (Realistic) ──

    async def _generate_sadtalker(
        self, audio_path: str, output_dir: Path,
        image_path: Optional[str], preset: str
    ) -> dict:
        source_image = image_path or str(self._get_preset_path(preset))
        if not Path(source_image).exists():
            source_image = str(self._get_preset_path("default"))

        video_path = output_dir / "avatar_video.mp4"

        if shutil.which("python") and self._check_sadtalker():
            cmd = [
                "python", "inference.py",
                "--driven_audio", str(audio_path),
                "--source_image", str(source_image),
                "--result_dir", str(output_dir),
                "--still",
                "--preprocess", "crop",
                "--enhancer", "gfpgan",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self._find_sadtalker_dir(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            generated = list(output_dir.glob("*.mp4"))
            if generated:
                generated[0].rename(video_path)
                return {
                    "video_file": "avatar_video.mp4",
                    "mode": "realistic",
                    "engine": "SadTalker",
                }

        # Fallback: generate animated avatar with the provided image
        return await self._generate_animated(audio_path, output_dir, preset)

    # ── Mode 3: Wav2Lip ──

    async def _generate_wav2lip(
        self, audio_path: str, output_dir: Path,
        image_path: Optional[str], preset: str
    ) -> dict:
        source = image_path or str(self._get_preset_path(preset))
        if not Path(source).exists():
            source = str(self._get_preset_path("default"))

        video_path = output_dir / "avatar_video.mp4"

        if shutil.which("python") and self._check_wav2lip():
            source_video = source
            if Path(source).suffix.lower() in (".png", ".jpg", ".jpeg"):
                source_video = str(output_dir / "static_face.mp4")
                await self._image_to_static_video(source, source_video, audio_path)

            cmd = [
                "python", "inference.py",
                "--checkpoint_path", "checkpoints/wav2lip_gan.pth",
                "--face", source_video,
                "--audio", str(audio_path),
                "--outfile", str(video_path),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self._find_wav2lip_dir(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if video_path.exists():
                return {
                    "video_file": "avatar_video.mp4",
                    "mode": "lipsync",
                    "engine": "Wav2Lip",
                }

        return await self._generate_animated(audio_path, output_dir, preset)

    # ── Helpers ──

    def _ensure_default_avatars(self):
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        default_path = self.avatars_dir / "default.png"
        if not default_path.exists():
            self._create_default_avatar(default_path)

    def _create_default_avatar(self, path: Path):
        """Create a simple cartoon avatar as the default preset."""
        size = 400
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Head
        draw.ellipse([50, 30, 350, 350], fill=(255, 210, 160), outline=(200, 160, 120), width=3)
        # Hair
        draw.ellipse([40, 10, 360, 200], fill=(50, 30, 20))
        draw.rectangle([40, 100, 360, 160], fill=(50, 30, 20))
        # Eyes
        draw.ellipse([120, 150, 170, 195], fill=(255, 255, 255))
        draw.ellipse([230, 150, 280, 195], fill=(255, 255, 255))
        draw.ellipse([135, 160, 155, 185], fill=(40, 40, 50))
        draw.ellipse([245, 160, 265, 185], fill=(40, 40, 50))
        # Nose
        draw.polygon([(200, 210), (190, 250), (210, 250)], fill=(235, 190, 140))
        # Smile
        draw.arc([150, 250, 250, 310], start=0, end=180, fill=(180, 60, 60), width=4)
        # Body
        draw.rectangle([130, 345, 270, 400], fill=(60, 120, 200))

        img.save(path, "PNG")

    def _load_avatar_image(self, preset: str) -> Image.Image:
        path = self._get_preset_path(preset)
        if path.exists():
            return Image.open(path).convert("RGBA").resize((400, 400))
        return Image.open(self.avatars_dir / "default.png").convert("RGBA").resize((400, 400))

    def _get_preset_path(self, preset: str) -> Path:
        for ext in (".png", ".jpg", ".jpeg"):
            p = self.avatars_dir / f"{preset}{ext}"
            if p.exists():
                return p
        return self.avatars_dir / "default.png"

    @staticmethod
    async def _get_audio_duration(audio_path: str) -> float:
        try:
            from pydub import AudioSegment
            audio = await asyncio.to_thread(AudioSegment.from_file, audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 30.0

    @staticmethod
    async def _frames_to_video(frames_dir: Path, audio_path: str, output_path: Path, fps: int):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found. Install FFmpeg and add to PATH.")

        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.png"),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

    @staticmethod
    async def _image_to_static_video(image_path: str, output_path: str, audio_path: str):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000.0

        cmd = [
            ffmpeg, "-y",
            "-loop", "1", "-i", str(image_path),
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

    @staticmethod
    def _check_sadtalker() -> bool:
        d = AvatarGenerator._find_sadtalker_dir()
        return d is not None and (Path(d) / "inference.py").exists()

    @staticmethod
    def _find_sadtalker_dir() -> Optional[str]:
        candidates = [
            os.environ.get("SADTALKER_DIR", ""),
            str(Path.home() / "SadTalker"),
            "./SadTalker",
        ]
        for c in candidates:
            if c and Path(c).is_dir():
                return c
        return None

    @staticmethod
    def _check_wav2lip() -> bool:
        d = AvatarGenerator._find_wav2lip_dir()
        return d is not None and (Path(d) / "inference.py").exists()

    @staticmethod
    def _find_wav2lip_dir() -> Optional[str]:
        candidates = [
            os.environ.get("WAV2LIP_DIR", ""),
            str(Path.home() / "Wav2Lip"),
            "./Wav2Lip",
        ]
        for c in candidates:
            if c and Path(c).is_dir():
                return c
        return None
