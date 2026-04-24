import asyncio
import json
import random
import re
from pathlib import Path
from typing import List, Tuple

import edge_tts

VOICES = {
    "hi-IN-MadhurNeural": "Male (Madhur)",
    "hi-IN-SwaraNeural": "Female (Swara)",
}

# Speech rate variation range (%) to sound natural
RATE_MIN, RATE_MAX = -8, +12
# Pitch variation range (Hz)
PITCH_MIN, PITCH_MAX = -15, +10


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
    text = re.sub(r"\b\d{3,}\b", "", text)
    text = re.sub(r"[^\w\s।,.!?…:\-\u0900-\u097F]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences, keeping Hindi punctuation."""
    parts = re.split(r"(?<=[।.!?।\n])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _build_ssml(sentences: List[str]) -> str:
    """Build SSML with varied rate, pitch, and natural pauses per sentence."""
    ssml_parts = ['<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="hi-IN">']

    for i, sentence in enumerate(sentences):
        rate_offset = random.randint(RATE_MIN, RATE_MAX)
        rate_str = f"+{rate_offset}%" if rate_offset >= 0 else f"{rate_offset}%"

        pitch_offset = random.randint(PITCH_MIN, PITCH_MAX)
        pitch_str = f"+{pitch_offset}Hz" if pitch_offset >= 0 else f"{pitch_offset}Hz"

        ssml_parts.append(
            f'<prosody rate="{rate_str}" pitch="{pitch_str}">'
            f"{sentence}"
            f"</prosody>"
        )

        if "..." in sentence:
            ssml_parts.append('<break time="600ms"/>')
        elif sentence.endswith(("!", "?")):
            pause = random.randint(350, 550)
            ssml_parts.append(f'<break time="{pause}ms"/>')
        else:
            pause = random.randint(200, 400)
            ssml_parts.append(f'<break time="{pause}ms"/>')

    ssml_parts.append("</speak>")
    return "".join(ssml_parts)


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
        sentences = _split_sentences(text)
        ssml = _build_ssml(sentences)

        communicate = edge_tts.Communicate(ssml, voice)
        subs: List[dict] = []

        # Generate audio and collect word-level timestamps
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
            "sentences": len(sentences),
            "voice_used": voice,
        }

    @staticmethod
    def available_voices() -> dict:
        return VOICES
