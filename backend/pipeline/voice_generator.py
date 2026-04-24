import asyncio
import io
import json
import random
import re
from pathlib import Path
from typing import List, Tuple

import edge_tts
from pydub import AudioSegment

VOICES = {
    "hi-IN-MadhurNeural": "Male (Madhur)",
    "hi-IN-SwaraNeural": "Female (Swara)",
}

GENRE_PROFILES = {
    "comedy": {
        "rate": (-8, 15),
        "pitch": (-10, 20),
        "pause": (300, 650),
        "punchline_pause": (600, 1000),
    },
    "motivational": {
        "rate": (-12, 8),
        "pitch": (-8, 18),
        "pause": (400, 850),
        "emphasis_pause": (700, 1100),
    },
    "educational": {
        "rate": (-10, 8),
        "pitch": (-8, 12),
        "pause": (350, 600),
        "concept_pause": (500, 800),
    },
}


def _clean_for_speech(text: str) -> str:
    """Strip everything a TTS engine should never read aloud."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"\{[\s\S]*?\}", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&\w+;", "", text)
    text = re.sub(r"#\S+", "", text)
    text = re.sub(r"@\S+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_~|<>{}()\[\]\"\\/#^=+]", "", text)
    text = re.sub(r"\b\d{5,}\b", "", text)
    text = re.sub(r"[^\w\s।,.!?…:\-\u0900-\u097F\u0980-\u09FF]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[।.!?\n])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _sentence_params(sentence: str, genre: str, idx: int, total: int) -> Tuple[int, int, int]:
    """Pick rate (%), pitch (Hz), and pause-after (ms) for one sentence."""
    profile = GENRE_PROFILES.get(genre, GENRE_PROFILES["comedy"])
    progress = idx / max(total - 1, 1)

    rate = random.randint(*profile["rate"])
    pitch = random.randint(*profile["pitch"])
    pause = random.randint(*profile["pause"])

    is_question = sentence.rstrip().endswith("?")
    is_exclaim = sentence.rstrip().endswith("!")
    is_ellipsis = "..." in sentence or "\u2026" in sentence
    word_count = len(sentence.split())
    is_short = word_count <= 5

    if genre == "comedy":
        if is_question:
            pitch += random.randint(5, 12)
            rate -= random.randint(3, 8)
        if is_short and idx > 0:
            pause = random.randint(*profile["punchline_pause"])
            rate -= random.randint(8, 18)
        elif is_exclaim:
            rate += random.randint(5, 12)
            pitch += random.randint(3, 8)
        if is_ellipsis:
            rate -= random.randint(5, 10)
            pause += random.randint(100, 300)

    elif genre == "motivational":
        rate += int(progress * 10)
        pitch += int(progress * 12)
        if is_short:
            pause = random.randint(*profile["emphasis_pause"])
            rate -= random.randint(6, 12)
            pitch += random.randint(3, 8)
        elif is_exclaim:
            pitch += random.randint(5, 12)

    elif genre == "educational":
        if is_question:
            pitch += random.randint(5, 10)
            pause += random.randint(100, 250)
        if word_count > 15:
            rate -= random.randint(4, 8)
        if is_exclaim:
            rate += random.randint(3, 7)

    rate = max(-20, min(25, rate))
    pitch = max(-25, min(30, pitch))
    pause = max(150, min(1400, pause))

    if idx == total - 1:
        pause = 0

    return rate, pitch, pause


async def _speak_sentence(text: str, voice: str, rate: int, pitch: int) -> Tuple[bytes, List[dict]]:
    """Generate audio bytes and word boundaries for a single sentence."""
    rate_s = f"+{rate}%" if rate >= 0 else f"{rate}%"
    pitch_s = f"+{pitch}Hz" if pitch >= 0 else f"{pitch}Hz"

    comm = edge_tts.Communicate(text, voice, rate=rate_s, pitch=pitch_s)
    audio = bytearray()
    words: List[dict] = []

    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append({
                "text": chunk["text"],
                "offset": chunk["offset"] // 10000,
                "duration": chunk["duration"] // 10000,
            })

    return bytes(audio), words


class VoiceGenerator:
    async def generate(
        self,
        text: str,
        voice: str = "hi-IN-MadhurNeural",
        output_dir: Path = None,
        genre: str = "comedy",
    ) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        audio_path = output_dir / "voiceover.mp3"
        subs_path = output_dir / "subtitles.json"

        text = _clean_for_speech(text)
        sentences = _split_sentences(text)
        if not sentences:
            raise ValueError("No speakable text found after cleaning")

        combined = AudioSegment.empty()
        all_subs: List[dict] = []
        cursor_ms = 0

        for i, sentence in enumerate(sentences):
            rate, pitch, pause_after = _sentence_params(sentence, genre, i, len(sentences))

            raw_mp3, word_hits = await _speak_sentence(sentence, voice, rate, pitch)

            if not raw_mp3:
                continue

            segment = AudioSegment.from_mp3(io.BytesIO(raw_mp3))

            for w in word_hits:
                all_subs.append({
                    "text": w["text"],
                    "offset_ms": cursor_ms + w["offset"],
                    "duration_ms": w["duration"],
                })

            combined += segment
            cursor_ms += len(segment)

            if pause_after > 0:
                combined += AudioSegment.silent(duration=pause_after)
                cursor_ms += pause_after

        combined.export(str(audio_path), format="mp3")

        with open(subs_path, "w", encoding="utf-8") as f:
            json.dump(all_subs, f, ensure_ascii=False, indent=2)

        duration_sec = len(combined) / 1000.0

        return {
            "audio_file": "voiceover.mp3",
            "subtitles_file": "subtitles.json",
            "word_count": len(all_subs),
            "sentences": len(sentences),
            "duration_seconds": round(duration_sec, 1),
            "genre": genre,
            "voice_used": voice,
        }

    @staticmethod
    def available_voices() -> dict:
        return VOICES
