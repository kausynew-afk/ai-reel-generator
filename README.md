# AI Reel Generator

Create viral YouTube & Instagram Reels with AI-generated scripts, Hindi voiceover, animated/realistic avatars, BGM, and anti-detection post-processing.

## Quick Start

### Prerequisites
- Python 3.9+
- FFmpeg (install and add to PATH)

### Setup

```bash
cd ai-reel-generator/backend
pip install -r requirements.txt
```

### Configure Script Generation

**Option A - Google Gemini (free, recommended):**
1. Get a free API key from https://makersuite.google.com/app/apikey
2. Create a file `backend/.gemini_key` with your key, OR set env var:
   ```bash
   set GEMINI_API_KEY=your_key_here
   ```

**Option B - Ollama (fully local):**
1. Install Ollama from https://ollama.ai
2. Run: `ollama pull llama3`
3. Select "Ollama (Local)" in the UI

### Run

```bash
cd ai-reel-generator/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000 in your browser.

## Pipeline Steps

| Step | What it does | Tool |
|------|-------------|------|
| 1. Script | AI generates reel script in Hindi | Gemini / Ollama |
| 2. Voice | Hindi text-to-speech with natural variations | edge-tts |
| 3. Avatar | Animated character, SadTalker, or Wav2Lip | PIL / SadTalker / Wav2Lip |
| 4. BGM | Background music selection or generation | Bundled library / Synthesis |
| 5. Compose | Combine video + voice + BGM + captions | FFmpeg |
| 6. Finalize | Anti-detection filters + metadata strip | FFmpeg |

## Optional: SadTalker / Wav2Lip

For realistic avatar modes, clone these repos and set env vars:

```bash
set SADTALKER_DIR=C:\path\to\SadTalker
set WAV2LIP_DIR=C:\path\to\Wav2Lip
```

Without them, the app falls back to the built-in animated character mode.
