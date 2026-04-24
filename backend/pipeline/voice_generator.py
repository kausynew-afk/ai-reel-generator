import asyncio
import json
import random
import re
from pathlib import Path
from typing import List

import edge_tts

VOICES = {
    "hi-IN-MadhurNeural": "Male (Madhur)",
    "hi-IN-SwaraNeural": "Female (Swara)",
}


def _clean_for_speech(text: str) -> str:
    """Strip everything a TTS engine should never read aloud."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\{[\s\S]*?\}", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"#\S+", "", text)
    text = re.sub(r"@\S+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_~|<>{}()\[\]\"\\/#^=+]", "", text)
    text = re.sub(r"\b\d{5,}\b", "", text)
    text = re.sub(r"[^\w\s।,.!?…:\-\u0900-\u097F\u0980-\u09FF]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


class VoiceGenerator:
    async def generate(
        self,
        text: str,
        voice: str = "hi-IN-MadhurNeural",
        output_dir: Path = None,
    ) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        audio_path = output_dir / "voiceover.mp3"
        subs_path = output_dir / "subtitles.json"

        text = _clean_for_speech(text)

        rate_offset = random.randint(-5, 10)
        rate_str = f"+{rate_offset}%" if rate_offset >= 0 else f"{rate_offset}%"

        pitch_offset = random.randint(-10, 5)
        pitch_str = f"+{pitch_offset}Hz" if pitch_offset >= 0 else f"{pitch_offset}Hz"

        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=rate_str,
            pitch=pitch_str,
        )

        subs: List[dict] = []

        with open(audio_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    subs.append(
                        {
                            "text": chunk["text"],
                            "offset_ms": chunk["offset"] // 10000,
                            "duration_ms": chunk["duration"] // 10000,
                        }
                    )

        with open(subs_path, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)

        return {
            "audio_file": "voiceover.mp3",
            "subtitles_file": "subtitles.json",
            "word_count": len(subs),
            "sentences": len(re.split(r"[।.!?\n]+", text)),
            "voice_used": voice,
        }

    @staticmethod
    def available_voices() -> dict:
        return VOICES
