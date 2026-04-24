import os
import uuid
import json
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pipeline.script_generator import ScriptGenerator
from pipeline.voice_generator import VoiceGenerator
from pipeline.avatar_generator import AvatarGenerator
from pipeline.bgm_generator import BGMGenerator
from pipeline.video_composer import VideoComposer
from pipeline.anti_detect import AntiDetect

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR.parent / "output"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI Reel Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR.parent / "frontend")), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

script_gen = ScriptGenerator()
voice_gen = VoiceGenerator()
avatar_gen = AvatarGenerator(assets_dir=ASSETS_DIR)
bgm_gen = BGMGenerator(assets_dir=ASSETS_DIR)
video_composer = VideoComposer()
anti_detect = AntiDetect()


@app.get("/")
async def serve_frontend():
    return FileResponse(str(BASE_DIR.parent / "frontend" / "index.html"))


# ── Step 1: Script Generation ──

@app.post("/api/script/generate")
async def generate_script(
    topic: str = Form(...),
    tone: str = Form("comedy"),
    duration: int = Form(30),
    provider: str = Form("gemini"),
):
    try:
        result = await script_gen.generate(
            topic=topic, tone=tone, duration_sec=duration, provider=provider
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Step 2: Voice Generation ──

@app.post("/api/voice/generate")
async def generate_voice(
    script: str = Form(...),
    voice: str = Form("hi-IN-MadhurNeural"),
    session_id: str = Form(None),
):
    sid = session_id or str(uuid.uuid4())
    session_dir = OUTPUT_DIR / sid
    session_dir.mkdir(exist_ok=True)
    try:
        result = await voice_gen.generate(
            text=script, voice=voice, output_dir=session_dir
        )
        result["session_id"] = sid
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Step 3: Avatar Video Generation ──

@app.post("/api/avatar/generate")
async def generate_avatar(
    session_id: str = Form(...),
    mode: str = Form("animated"),
    avatar_preset: str = Form("default"),
    avatar_image: UploadFile = File(None),
):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    image_path = None
    if avatar_image and avatar_image.filename:
        image_path = session_dir / f"avatar_input_{avatar_image.filename}"
        with open(image_path, "wb") as f:
            content = await avatar_image.read()
            f.write(content)

    audio_path = session_dir / "voiceover.mp3"
    if not audio_path.exists():
        raise HTTPException(status_code=400, detail="Generate voiceover first")

    try:
        result = await avatar_gen.generate(
            mode=mode,
            audio_path=str(audio_path),
            output_dir=str(session_dir),
            image_path=str(image_path) if image_path else None,
            preset=avatar_preset,
        )
        result["session_id"] = session_id
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/avatar/presets")
async def list_avatar_presets():
    presets = avatar_gen.list_presets()
    return JSONResponse({"presets": presets})


# ── Step 4: BGM ──

@app.post("/api/bgm/select")
async def select_bgm(
    session_id: str = Form(...),
    category: str = Form("comedy"),
    custom_prompt: str = Form(None),
):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await bgm_gen.select(
            category=category,
            output_dir=str(session_dir),
            custom_prompt=custom_prompt,
        )
        result["session_id"] = session_id
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bgm/library")
async def list_bgm_library():
    library = bgm_gen.list_library()
    return JSONResponse({"tracks": library})


# ── Step 5: Compose Final Video ──

@app.post("/api/video/compose")
async def compose_video(
    session_id: str = Form(...),
    add_captions: bool = Form(True),
    caption_style: str = Form("word_highlight"),
):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await video_composer.compose(
            session_dir=str(session_dir),
            add_captions=add_captions,
            caption_style=caption_style,
        )
        result["session_id"] = session_id
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Step 6: Anti-Detection Post-Processing ──

@app.post("/api/video/finalize")
async def finalize_video(
    session_id: str = Form(...),
    grain_intensity: float = Form(0.02),
    audio_room_tone: bool = Form(True),
):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        result = await anti_detect.process(
            session_dir=str(session_dir),
            grain_intensity=grain_intensity,
            audio_room_tone=audio_room_tone,
        )
        result["session_id"] = session_id
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Utilities ──

@app.get("/api/session/{session_id}/files")
async def list_session_files(session_id: str):
    session_dir = OUTPUT_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    files = [f.name for f in session_dir.iterdir() if f.is_file()]
    return JSONResponse({"files": files, "session_id": session_id})


@app.get("/api/session/{session_id}/download/{filename}")
async def download_file(session_id: str, filename: str):
    file_path = OUTPUT_DIR / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), filename=filename)


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    session_dir = OUTPUT_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir)
    return JSONResponse({"status": "deleted", "session_id": session_id})


# ── Tunnel for Mobile Access ──

_tunnel_process = None
_tunnel_url = None


@app.post("/api/tunnel/start")
async def start_tunnel():
    global _tunnel_process, _tunnel_url
    if _tunnel_process is not None and _tunnel_process.returncode is None:
        return JSONResponse({"status": "already_running", "url": _tunnel_url})

    # Try multiple free SSH-based tunnel services (bypass corporate TLS proxies)
    tunnel_cmds = [
        {
            "name": "localhost.run",
            "cmd": ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
                    "-R", "80:localhost:8000", "nokey@localhost.run"],
            "pattern": r"(https://[a-z0-9]+\.lhr\.life\S*)",
        },
        {
            "name": "serveo.net",
            "cmd": ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
                    "-R", "80:localhost:8000", "serveo.net"],
            "pattern": r"(https://[a-z0-9]+\.serveo\.net)",
        },
    ]

    import asyncio, re, subprocess

    for svc in tunnel_cmds:
        try:
            proc = await asyncio.create_subprocess_exec(
                *svc["cmd"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
            )
            # Read output for up to 15 seconds looking for the public URL
            url = None
            for _ in range(30):
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                    decoded = line.decode(errors="ignore")
                    match = re.search(svc["pattern"], decoded)
                    if match:
                        url = match.group(1)
                        break
                except asyncio.TimeoutError:
                    continue

            if url:
                _tunnel_process = proc
                _tunnel_url = url
                return JSONResponse({
                    "status": "started", "url": url, "service": svc["name"]
                })
            else:
                proc.kill()
        except Exception:
            continue

    # Fallback: try ngrok with TLS verification disabled
    try:
        from pyngrok import ngrok, conf
        pyngrok_config = conf.PyngrokConfig()
        pyngrok_config.monitor_thread = False
        tunnel = ngrok.connect(8000, "http", pyngrok_config=pyngrok_config)
        _tunnel_url = tunnel.public_url
        return JSONResponse({"status": "started", "url": _tunnel_url, "service": "ngrok"})
    except Exception as e:
        pass

    raise HTTPException(
        status_code=500,
        detail="Could not start tunnel. On corporate networks, tunneling may be blocked. "
               "Try on a personal machine or use http://YOUR_IP:8000 on the same WiFi."
    )


@app.delete("/api/tunnel/stop")
async def stop_tunnel():
    global _tunnel_process, _tunnel_url
    if _tunnel_process is not None:
        try:
            _tunnel_process.kill()
        except Exception:
            pass
        _tunnel_process = None
    _tunnel_url = None
    try:
        from pyngrok import ngrok
        ngrok.kill()
    except Exception:
        pass
    return JSONResponse({"status": "stopped"})


@app.get("/api/tunnel/status")
async def tunnel_status():
    active = _tunnel_process is not None and _tunnel_process.returncode is None
    if not active and _tunnel_url:
        active = True
    return JSONResponse({"active": active, "url": _tunnel_url if active else None})
