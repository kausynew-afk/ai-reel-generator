import asyncio
import json
import math
import shutil
import struct
import wave
from pathlib import Path
from typing import Optional, List

import numpy as np


CATEGORIES = ["comedy", "motivational", "dramatic", "chill", "action", "romantic"]


class BGMGenerator:
    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        self.bgm_dir = self.assets_dir / "bgm"
        self.bgm_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_bundled_tracks()

    async def select(
        self,
        category: str,
        output_dir: str,
        custom_prompt: Optional[str] = None,
    ) -> dict:
        output_dir = Path(output_dir)

        if custom_prompt:
            return await self._generate_procedural(custom_prompt, output_dir, category)

        track = self._pick_track(category)
        if track:
            dest = output_dir / "bgm.mp3"
            shutil.copy2(track, dest)
            return {
                "bgm_file": "bgm.mp3",
                "source": "library",
                "category": category,
                "track_name": track.stem,
            }

        return await self._generate_procedural(
            f"{category} background music for short video", output_dir, category
        )

    def list_library(self) -> List[dict]:
        tracks = []
        for f in sorted(self.bgm_dir.iterdir()):
            if f.suffix.lower() in (".mp3", ".wav", ".ogg"):
                cat = "unknown"
                for c in CATEGORIES:
                    if c in f.stem.lower():
                        cat = c
                        break
                tracks.append({"name": f.stem, "filename": f.name, "category": cat})
        return tracks

    def _pick_track(self, category: str) -> Optional[Path]:
        matches = [
            f for f in self.bgm_dir.iterdir()
            if f.suffix.lower() in (".mp3", ".wav", ".ogg")
            and category.lower() in f.stem.lower()
        ]
        if matches:
            import random
            return random.choice(matches)
        all_tracks = [
            f for f in self.bgm_dir.iterdir()
            if f.suffix.lower() in (".mp3", ".wav", ".ogg")
        ]
        if all_tracks:
            import random
            return random.choice(all_tracks)
        return None

    async def _generate_procedural(
        self, prompt: str, output_dir: Path, category: str
    ) -> dict:
        """Generate a simple procedural BGM using sine-wave synthesis."""
        output_path = output_dir / "bgm.wav"

        await asyncio.to_thread(
            self._synthesize_bgm, category, str(output_path)
        )

        mp3_path = output_dir / "bgm.mp3"
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg, "-y", "-i", str(output_path),
                "-b:a", "192k", str(mp3_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if mp3_path.exists():
                output_path.unlink(missing_ok=True)
                return {
                    "bgm_file": "bgm.mp3",
                    "source": "generated",
                    "category": category,
                }

        return {
            "bgm_file": "bgm.wav",
            "source": "generated",
            "category": category,
        }

    @staticmethod
    def _synthesize_bgm(category: str, output_path: str, duration_sec: float = 60.0):
        """Create a pleasant looping BGM from layered sine waves."""
        sample_rate = 44100
        total_samples = int(sample_rate * duration_sec)

        presets = {
            "comedy": {
                "tempo": 130, "key_freq": 261.63,
                "scale": [1, 1.25, 1.5, 1.667, 2],
                "vol": 0.3,
            },
            "motivational": {
                "tempo": 90, "key_freq": 220.0,
                "scale": [1, 1.2, 1.5, 1.8, 2],
                "vol": 0.25,
            },
            "dramatic": {
                "tempo": 70, "key_freq": 196.0,
                "scale": [1, 1.189, 1.498, 1.682, 2],
                "vol": 0.28,
            },
            "chill": {
                "tempo": 80, "key_freq": 293.66,
                "scale": [1, 1.125, 1.334, 1.5, 1.782],
                "vol": 0.2,
            },
        }

        p = presets.get(category, presets["chill"])
        t = np.linspace(0, duration_sec, total_samples, dtype=np.float32)

        signal = np.zeros(total_samples, dtype=np.float32)

        # Pad / chord layer
        for ratio in p["scale"][:3]:
            freq = p["key_freq"] * ratio
            signal += 0.15 * np.sin(2 * np.pi * freq * t)

        # Rhythmic pulse
        beat_period = 60.0 / p["tempo"]
        beat_env = np.abs(np.sin(np.pi * t / beat_period)) ** 4
        kick_freq = p["key_freq"] * 0.5
        signal += 0.2 * beat_env * np.sin(2 * np.pi * kick_freq * t * np.exp(-t % beat_period * 8))

        # Arpeggio
        arp_period = beat_period / 2
        for i, ratio in enumerate(p["scale"]):
            phase = (t + i * arp_period / len(p["scale"])) % (arp_period * len(p["scale"]))
            mask = ((phase >= i * arp_period) & (phase < (i + 1) * arp_period)).astype(np.float32)
            env = mask * np.exp(-((phase - i * arp_period) / arp_period) * 3)
            signal += 0.1 * env * np.sin(2 * np.pi * p["key_freq"] * ratio * 2 * t)

        # Normalize and apply master volume
        peak = np.max(np.abs(signal))
        if peak > 0:
            signal = signal / peak * p["vol"]

        signal = np.clip(signal, -1.0, 1.0)
        pcm = (signal * 32767).astype(np.int16)

        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

    def _ensure_bundled_tracks(self):
        """Create placeholder BGM files if none exist."""
        if any(self.bgm_dir.iterdir()):
            return
        for cat in CATEGORIES:
            path = self.bgm_dir / f"{cat}_default.wav"
            self._synthesize_bgm(cat, str(path), duration_sec=60.0)
