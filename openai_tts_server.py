#!/usr/bin/env python3
"""
OpenAI-Compatible TTS API Server using pocket-tts
Minimal dependencies: uvicorn, fastapi, pocket-tts, soundfile
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Any, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict
import soundfile as sf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import pocket_tts
try:
    from pocket_tts import TTSModel
    POCKET_TTS_AVAILABLE = True
except ImportError as e:
    POCKET_TTS_AVAILABLE = False
    logger.error(f"pocket-tts not available: {e}")

# Configuration
PORT = int(os.getenv("PORT", "8000"))
CACHE_DIR = os.getenv("CACHE_DIR", "./tts_cache")
VOICES_DIR = os.getenv("VOICES_DIR", "./voices")
MAX_CACHE_FILES = int(os.getenv("MAX_CACHE", "100"))

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(VOICES_DIR, exist_ok=True)

# Voice mapping: OpenAI names -> pocket-tts names
VOICE_MAPPING = {
    "alloy": "alba",
    "echo": "jean",
    "fable": "fantine", 
    "onyx": "cosette",
    "nova": "eponine",
    "shimmer": "azelma",
}

BUILTIN_VOICES = ["alba", "marius", "javert", "jean", "fantine", "cosette", "eponine", "azelma"]

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
    "opus": "audio/opus",
    "flac": "audio/flac",
    "pcm": "audio/pcm",
}

FFMPEG_FORMATS = {
    "mp3": ("mp3", "libmp3lame"),
    "opus": ("ogg", "opus"),
    "aac": ("adts", "aac"),
    "flac": ("flac", "flac"),
}


class SpeechRequest(BaseModel):
    """OpenAI-compatible speech request - permissive for OpenWebUI"""
    model_config = ConfigDict(extra="ignore")  # Ignore extra fields
    
    model: Optional[str] = Field(default="tts-1")
    input: str = Field(...)
    voice: str = Field(default="alloy")
    response_format: Optional[str] = Field(default="mp3")
    speed: Optional[float] = Field(default=1.0)
    
    @field_validator("voice", mode="before")
    @classmethod
    def map_voice(cls, v: Any) -> str:
        if v is None or v == "":
            return "alloy"
        v = str(v).strip()
        return VOICE_MAPPING.get(v, v)
    
    @field_validator("input", mode="before")
    @classmethod
    def validate_input(cls, v: Any) -> str:
        if v is None:
            raise ValueError("input is required")
        s = str(v).strip()
        if not s:
            raise ValueError("input cannot be empty")
        return s
    
    @field_validator("response_format", mode="before")
    @classmethod
    def validate_format(cls, v: Any) -> str:
        if v is None or v == "":
            return "mp3"
        v = str(v).lower()
        valid = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
        return v if v in valid else "mp3"
    
    @field_validator("speed", mode="before")
    @classmethod
    def validate_speed(cls, v: Any) -> float:
        if v is None:
            return 1.0
        try:
            f = float(v)
            return max(0.25, min(4.0, f))
        except (TypeError, ValueError):
            return 1.0


# Global state
tts_model: Optional[TTSModel] = None
voice_states: dict = {}
model_lock = asyncio.Lock()


def tensor_to_numpy(audio_tensor):
    """Convert tensor to numpy array without explicit numpy import if possible"""
    # If it's already a numpy array
    if hasattr(audio_tensor, '__array__'):
        return audio_tensor.__array__()
    # If it has a numpy method (torch tensor)
    if hasattr(audio_tensor, 'numpy'):
        return audio_tensor.numpy()
    # If it's a list or other sequence
    if hasattr(audio_tensor, '__iter__'):
        # Try to convert using soundfile's buffer handling
        return audio_tensor
    return audio_tensor


def flatten_audio(audio_data):
    """Flatten multi-dimensional audio to 1D"""
    # Handle different input types
    if hasattr(audio_data, 'flatten'):
        return audio_data.flatten()
    if hasattr(audio_data, 'reshape'):
        # Try to reshape to 1D
        size = 1
        for dim in audio_data.shape:
            size *= dim
        return audio_data.reshape(size)
    # If it's a list of lists, flatten manually
    if isinstance(audio_data, (list, tuple)) and len(audio_data) > 0 and isinstance(audio_data[0], (list, tuple)):
        return [item for sublist in audio_data for item in sublist]
    return audio_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load TTS model on startup"""
    global tts_model
    
    if not POCKET_TTS_AVAILABLE:
        logger.error("❌ pocket-tts not available")
        yield
        return
    
    logger.info("🚀 Loading Pocket TTS model...")
    try:
        loop = asyncio.get_event_loop()
        tts_model = await loop.run_in_executor(None, TTSModel.load_model)
        logger.info(f"✅ Model loaded on device: {tts_model.device}")
        
        # Pre-load default voice
        logger.info("🎙️  Pre-loading default voice...")
        default_state = await loop.run_in_executor(
            None, 
            lambda: tts_model.get_state_for_audio_prompt("alba")
        )
        voice_states["alba"] = default_state
        logger.info("✅ Ready")
        
    except Exception as e:
        logger.exception("Failed to load model")
        raise
    
    yield
    
    logger.info("🛑 Shutting down...")


app = FastAPI(
    title="OpenAI-Compatible TTS API",
    description="OpenAI Audio API for pocket-tts",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and return proper error response"""
    logger.error(f"Global error: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__}
    )


def get_cache_key(text: str, voice: str, format: str, speed: float) -> str:
    """Generate cache key"""
    key = f"{text}|{voice}|{format}|{speed}|v1"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


async def get_or_create_voice_state(voice: str) -> any:
    """Get cached voice state or create new one"""
    if voice in voice_states:
        return voice_states[voice]
    
    if voice in BUILTIN_VOICES:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(
            None,
            lambda: tts_model.get_state_for_audio_prompt(voice)
        )
        voice_states[voice] = state
        return state
    
    # Check for custom voice
    voice_path = None
    if os.path.exists(os.path.join(VOICES_DIR, f"{voice}.wav")):
        voice_path = os.path.join(VOICES_DIR, f"{voice}.wav")
    elif os.path.exists(os.path.join(VOICES_DIR, f"{voice}.safetensors")):
        voice_path = os.path.join(VOICES_DIR, f"{voice}.safetensors")
    elif os.path.exists(voice):
        voice_path = voice
    
    if not voice_path:
        # Fallback to alba if voice not found
        logger.warning(f"Voice '{voice}' not found, using 'alba'")
        return await get_or_create_voice_state("alba")
    
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(
        None,
        lambda: tts_model.get_state_for_audio_prompt(voice_path)
    )
    voice_states[voice] = state
    return state


async def generate_audio(text: str, voice: str) -> bytes:
    """Generate raw WAV audio"""
    if not tts_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    voice_state = await get_or_create_voice_state(voice)
    loop = asyncio.get_event_loop()
    
    def _generate():
        audio = tts_model.generate_audio(voice_state, text)
        buffer = io.BytesIO()
        
        # Convert tensor/array to format soundfile can handle
        audio_data = tensor_to_numpy(audio)
        audio_data = flatten_audio(audio_data)
        
        # Ensure it's a proper array format for soundfile
        # soundfile can handle lists, numpy arrays, and buffer objects
        sf.write(buffer, audio_data, tts_model.sample_rate, format='WAV')
        return buffer.getvalue()
    
    return await loop.run_in_executor(None, _generate)


def convert_audio_format(wav_data: bytes, target_format: str, speed: float) -> bytes:
    """Convert audio format using ffmpeg"""
    if target_format == "wav" and speed == 1.0:
        return wav_data
    
    if target_format == "pcm":
        # Strip WAV header (first 44 bytes) to get raw PCM
        return wav_data[44:] if len(wav_data) > 44 else wav_data
    
    if target_format not in FFMPEG_FORMATS:
        return wav_data
    
    out_fmt, codec = FFMPEG_FORMATS[target_format]
    
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-f", "wav", "-i", "pipe:0",
    ]
    
    if speed != 1.0:
        cmd.extend(["-filter:a", f"atempo={speed}"])
    
    if target_format == "mp3":
        cmd.extend(["-ar", "44100", "-q:a", "0"])
    elif target_format in ("aac", "opus"):
        cmd.extend(["-b:a", "192k"])
    
    if codec == "opus":
        cmd.extend(["-strict", "-2"])
    
    cmd.extend(["-f", out_fmt, "-codec:a", codec, "pipe:1"])
    
    try:
        result = subprocess.run(cmd, input=wav_data, capture_output=True, timeout=30)
        if result.returncode == 0:
            return result.stdout
        logger.error(f"FFmpeg error: {result.stderr.decode()}")
    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
    
    return wav_data


@app.get("/v1/voices")
async def list_voices():
    """List available voices"""
    voices = []
    
    for openai_name, pocket_name in VOICE_MAPPING.items():
        voices.append({
            "voice_id": openai_name,
            "name": f"{pocket_name.title()} ({openai_name})",
            "preview_url": None,
        })
    
    for v in BUILTIN_VOICES:
        if v not in VOICE_MAPPING.values():
            voices.append({
                "voice_id": v,
                "name": v.title(),
                "preview_url": None,
            })
    
    return {"voices": voices, "object": "list"}


@app.post("/v1/audio/speech")
async def create_speech(
    request: Request,
    background_tasks: BackgroundTasks
):
    """OpenAI-compatible speech endpoint with raw request logging"""
    # Log raw request for debugging
    try:
        body = await request.body()
        logger.info(f"Raw request body: {body.decode()}")
        
        # Parse JSON manually to handle edge cases
        data = json.loads(body) if body else {}
    except Exception as e:
        logger.error(f"Failed to parse request: {e}")
        data = {}
    
    # Convert to our model
    try:
        speech_req = SpeechRequest(**data)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return JSONResponse(
            status_code=422,
            content={"error": "Validation error", "details": str(e)}
        )
    
    if not POCKET_TTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="pocket-tts not installed")
    
    pocket_voice = VOICE_MAPPING.get(speech_req.voice, speech_req.voice)
    
    # Check cache
    cache_key = get_cache_key(
        speech_req.input, pocket_voice, speech_req.response_format, speech_req.speed
    )
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.{speech_req.response_format}")
    
    if os.path.exists(cache_file):
        logger.info(f"Cache hit: {cache_key[:8]}...")
        async def stream_cached():
            with open(cache_file, "rb") as f:
                while chunk := f.read(64 * 1024):
                    yield chunk
        return StreamingResponse(
            stream_cached(),
            media_type=MEDIA_TYPES.get(speech_req.response_format, "audio/mpeg")
        )
    
    # Generate
    logger.info(f"Generating: voice={pocket_voice}, format={speech_req.response_format}")
    
    async with model_lock:
        wav_data = await generate_audio(speech_req.input, pocket_voice)
    
    final_data = convert_audio_format(wav_data, speech_req.response_format, speech_req.speed)
    
    # Save cache
    def save_cache():
        with open(cache_file, "wb") as f:
            f.write(final_data)
        cleanup_old_cache()
    
    background_tasks.add_task(save_cache)
    
    # Stream
    async def stream_response():
        chunk_size = 64 * 1024
        for i in range(0, len(final_data), chunk_size):
            yield final_data[i:i + chunk_size]
    
    return StreamingResponse(
        stream_response(),
        media_type=MEDIA_TYPES.get(speech_req.response_format, "audio/mpeg"),
        headers={
            "Content-Type": MEDIA_TYPES.get(speech_req.response_format, "audio/mpeg"),
            "Transfer-Encoding": "chunked",
        }
    )


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy" if tts_model else "loading",
        "model_loaded": tts_model is not None,
        "cached_voices": list(voice_states.keys()),
    }


@app.get("/")
async def root():
    """API info"""
    return {
        "name": "OpenAI-Compatible TTS API",
        "version": "1.0.0",
        "endpoints": {
            "speech": "/v1/audio/speech",
            "voices": "/v1/voices",
            "health": "/health"
        }
    }


def cleanup_old_cache():
    """Remove old cache files"""
    try:
        files = [(os.path.join(CACHE_DIR, f), os.path.getmtime(os.path.join(CACHE_DIR, f))) 
                 for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f))]
        
        if len(files) > MAX_CACHE_FILES:
            files.sort(key=lambda x: x[1])
            for old_path, _ in files[:-MAX_CACHE_FILES]:
                try:
                    os.remove(old_path)
                except OSError:
                    pass
    except Exception as e:
        logger.error(f"Cache cleanup error: {e}")


if __name__ == "__main__":
    if not POCKET_TTS_AVAILABLE:
        print("❌ Error: pocket-tts not available")
        sys.exit(1)
    
    print(f"""
╔════════════════════════════════════════════════════════════╗
║  OpenAI-Compatible TTS API (pocket-tts)                    ║
╠════════════════════════════════════════════════════════════╣
║  Server:     http://localhost:{PORT}                         ║
╠════════════════════════════════════════════════════════════╣
║  Ready for OpenWebUI!                                      ║
╠════════════════════════════════════════════════════════════╣
║  Voices: OpenAI  -> pocket-tts                             ║
║                                                            ║
║   alloy   -> alba                                          ║
║   echo    -> jean                                          ║
║   fable   -> fantine                                       ║
║   onyx    -> cosette                                       ║
║   nova    -> eponine                                       ║
║   shimmer -> azelma                                        ║
║           -> marius                                        ║
║           -> javert                                        ║
║  Every voice can be used.                                  ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
