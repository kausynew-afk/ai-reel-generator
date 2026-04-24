import json
import re
import asyncio
from typing import Optional

TONE_PROMPTS = {
    "comedy": "Make it funny, witty, and entertaining with punchy humor. Use Hindi slang and relatable jokes.",
    "motivational": "Make it deeply inspiring and powerful. Use emotional storytelling that moves people.",
    "educational": "Make it informative and fascinating. Present facts in an engaging, mind-blowing way.",
    "dramatic": "Make it intense and gripping like a thriller. Build suspense and tension.",
    "roast": "Make it savage and brutally funny. Roast the topic with sharp observations.",
    "storytelling": "Tell a captivating short story. Hook them from the first line.",
}

SYSTEM_PROMPT = """You are an expert short-form video scriptwriter for Instagram Reels and YouTube Shorts.
You write scripts in Hindi (Devanagari script) that go viral.

Rules:
1. Hook must grab attention in the first 2 seconds
2. Keep sentences SHORT and punchy - one idea per sentence
3. Write ONLY the spoken dialogue - no stage directions
4. End with a strong call-to-action or memorable punchline
5. The script must be naturally spoken Hindi (not overly formal)
6. Include appropriate pauses marked with "..." for dramatic effect

Return your response as valid JSON with this exact structure:
{
  "title": "Short catchy title for the reel",
  "hook": "The opening hook line (first 2 seconds)",
  "body": ["Line 1", "Line 2", "Line 3", ...],
  "cta": "Call to action or closing punchline",
  "caption": "Instagram/YouTube caption with hashtags",
  "estimated_duration_sec": 30
}
"""


def _build_user_prompt(topic: str, tone: str, duration_sec: int) -> str:
    tone_instruction = TONE_PROMPTS.get(tone, TONE_PROMPTS["comedy"])
    return (
        f"Write a {duration_sec}-second reel script about: {topic}\n\n"
        f"Tone: {tone_instruction}\n\n"
        f"Target duration: ~{duration_sec} seconds when spoken aloud in Hindi.\n"
        f"Keep it concise - roughly {duration_sec // 5} to {duration_sec // 3} lines total."
    )


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group())
        return {
            "title": "Untitled",
            "hook": "",
            "body": [cleaned],
            "cta": "",
            "caption": "",
            "estimated_duration_sec": 30,
        }


async def _generate_with_gemini(topic: str, tone: str, duration_sec: int) -> dict:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("Install google-generativeai: pip install google-generativeai")

    api_key = _get_gemini_key()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = _build_user_prompt(topic, tone, duration_sec)
    response = await asyncio.to_thread(
        model.generate_content, f"{SYSTEM_PROMPT}\n\n{prompt}"
    )
    return _parse_llm_response(response.text)


async def _generate_with_ollama(topic: str, tone: str, duration_sec: int) -> dict:
    import requests

    prompt = _build_user_prompt(topic, tone, duration_sec)
    payload = {
        "model": "llama3",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    resp = await asyncio.to_thread(
        requests.post,
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    return _parse_llm_response(raw)


def _get_gemini_key() -> str:
    import os

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        key_file = Path(__file__).resolve().parent.parent / ".gemini_key"
        if key_file.exists():
            key = key_file.read_text().strip()
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY env var or create backend/.gemini_key file"
        )
    return key


from pathlib import Path


class ScriptGenerator:
    async def generate(
        self,
        topic: str,
        tone: str = "comedy",
        duration_sec: int = 30,
        provider: str = "gemini",
    ) -> dict:
        if provider == "ollama":
            script = await _generate_with_ollama(topic, tone, duration_sec)
        elif provider == "gemini":
            script = await _generate_with_gemini(topic, tone, duration_sec)
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'gemini' or 'ollama'.")

        full_script = self._assemble_full_text(script)
        script["full_script"] = full_script
        return script

    @staticmethod
    def _assemble_full_text(script: dict) -> str:
        parts = []
        if script.get("hook"):
            parts.append(script["hook"])
        for line in script.get("body", []):
            parts.append(line)
        if script.get("cta"):
            parts.append(script["cta"])
        return "\n".join(parts)
