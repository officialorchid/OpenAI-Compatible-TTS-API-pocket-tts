# OpenAI-Compatible TTS API (pocket-tts)

A lightweight, **OpenAI-compatible Text-to-Speech API server** built with FastAPI and [pocket-tts](https://github.com/kyutai-labs/pocket-tts). This server provides a drop-in replacement for OpenAI's `/v1/audio/speech` endpoint, making it perfect for applications like **OpenWebUI**, **Home Assistant**, or any other tool that expects an OpenAI-compatible TTS API.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pocket TTS](https://img.shields.io/badge/powered%20by-pocket--tts-green.svg)](https://github.com/kyutai-labs/pocket-tts)

## ✨ Features

- 🔥 **OpenAI API Compatible** - Drop-in replacement for OpenAI's TTS endpoints
- 🚀 **No GPU Required** - Runs entirely on CPU (100M parameter model)
- ⚡ **Low Latency** - ~200ms to first audio chunk, 6x real-time generation
- 🎙️ **Voice Cloning** - Clone any voice from a 5-second audio sample
- 🐳 **Zero FFmpeg** - Pure Python implementation using only `soundfile` and `numpy`
- 🏠 **Self-Hosted** - 100% offline, no data leaves your machine
- 📦 **Lightweight** - Minimal dependencies: `uvicorn`, `fastapi`, `pocket-tts`, `soundfile`, `numpy`

## 🚀 Quick Start

### Prerequisites

- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/officialorchid/OpenAI-Compatible-TTS-API-pocket-tts.git
cd OpenAI-Compatible-TTS-API-pocket-tts

# Create virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Or use pip
#pip install -r requirements.txt
```

### Running the Server

```bash
# Start the API server
uv run openai_tts_server.py

# Or directly with Python
#python openai_tts_server.py
```

The server will start on `http://localhost:8000` by default.

## 🔧 Configuration

Configure the server using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `CACHE_DIR` | `./tts_cache` | Directory for cached audio files |
| `VOICES_DIR` | `./voices` | Directory for custom voice files |
| `MAX_CACHE` | `100` | Maximum cached files before cleanup |

Example:
```bash
PORT=8080 CACHE_DIR=/tmp/tts_cache python openai_tts_server.py
```

## 🎙️ Voices

### Built-in Voices (OpenAI-compatible mapping)

The server maps standard OpenAI voice names to pocket-tts equivalents:

| OpenAI Name | pocket-tts | Description |
|-------------|------------|-------------|
| `alloy` | `alba` | Female, clear and balanced |
| `echo` | `jean` | Male, warm tone |
| `fable` | `fantine` | Female, storytelling style |
| `onyx` | `cosette` | Female, elegant |
| `nova` | `eponine` | Female, youthful |
| `shimmer` | `azelma` | Female, bright |

### Additional Built-in Voices

- `marius` - Male voice
- `javert` - Male voice

### Custom Voices

Place your own `.wav` or `.safetensors` voice files in the `VOICES_DIR` directory. You can create `.safetensors` files for faster loading using pocket-tts's `export-voice` command:

```bash
# Export a voice for faster loading
pocket-tts export-voice --input my_voice.wav --output my_voice.safetensors
```

Then use it via the API:
```json
{
  "voice": "my_voice",
  "input": "Hello world!"
}
```

## 📡 API Endpoints

### `POST /v1/audio/speech`

Generate speech from text (OpenAI-compatible).

**Request Body:**
```json
{
  "model": "tts-1",
  "input": "Hello, this is a test of the text to speech system.",
  "voice": "alloy",
  "response_format": "mp3",
  "speed": 1.0
}
```

**Parameters:**
- `input` (required): The text to generate speech for
- `voice`: Voice to use (default: `alloy`)
- `response_format`: Audio format - `wav`, `flac`, `opus`, `pcm` (default: `mp3` → falls back to `wav`)
- `speed`: Speed multiplier 0.25-4.0 (default: `1.0`)

**Response:** Streaming audio data

### `GET /v1/voices`

List all available voices.

### `GET /health`

Health check endpoint showing model status and cached voices.

### `GET /`

API information and supported formats.

## 💡 Usage Examples

### cURL

```bash
# Generate speech with default voice
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello world!", "voice": "alloy"}' \
  --output speech.wav

# List available voices
curl http://localhost:8000/v1/voices
```

### Python (OpenAI SDK compatible)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # Local server doesn't require auth
)

response = client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input="Hello, this is a test!"
)

response.stream_to_file("output.wav")
```

### JavaScript/TypeScript

```javascript
const response = await fetch('http://localhost:8000/v1/audio/speech', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    input: 'Hello world!',
    voice: 'echo',
    response_format: 'wav'
  })
});

const blob = await response.blob();
const audio = new Audio(URL.createObjectURL(blob));
audio.play();
```

## 🏠 Integration with OpenWebUI

1. Go to **Settings** → **Audio** in OpenWebUI
2. Set **TTS API URL** to `http://localhost:8000/v1`
3. Set **TTS Voice** to any of the available voices (e.g., `alloy`, `echo`)
4. Set **TTS Model** to `tts-1`

## 🔊 Supported Audio Formats

| Format | Support | Notes |
|--------|---------|-------|
| `wav` | ✅ Native | Best compatibility |
| `flac` | ✅ Native | Lossless compression |
| `opus` | ✅ Native | Low bitrate, high quality |
| `pcm` | ✅ Native | Raw PCM data |
| `mp3` | ✅ Native | Best compatibility |
| `aac` | ✅ Native | Best compatibility |

## 🛠️ Architecture

This server uses a **pure Python** approach without external audio encoding tools:

- **Audio Generation**: `pocket-tts` (Kyutai Labs) - 100M parameter model
- **Audio Processing**: `numpy` for resampling and speed adjustment
- **Audio Encoding**: `soundfile` (libsndfile) for WAV/FLAC/Opus encoding
- **API Framework**: FastAPI with streaming responses
- **Speed Control**: NumPy-based resampling (no FFmpeg atempo filter needed)

## 📋 Requirements

```
uvicorn
fastapi
pocket-tts
soundfile
```

No FFmpeg, no GPU drivers, no cloud APIs. Just Python.

## 🔒 Privacy & Security

- **100% Offline**: No data ever leaves your machine
- **Local Processing**: All voice cloning and generation happens locally
- **No API Keys**: No external services or authentication required
- **Open Source**: MIT licensed, fully auditable code

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Kyutai Labs](https://kyutai.org/) for the incredible [pocket-tts](https://github.com/kyutai-labs/pocket-tts) model
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [soundfile](https://python-soundfile.readthedocs.io/) for audio encoding

## 📚 References

- [Pocket TTS Technical Report](https://kyutai.org/pocket-tts-technical-report)
- [Pocket TTS GitHub](https://github.com/kyutai-labs/pocket-tts)
- [OpenAI TTS API Documentation](https://platform.openai.com/docs/guides/text-to-speech)

---

**Made with ❤️ for the self-hosting community.**
