
```markdown
# OpenAI-Compatible TTS API (pocket-tts)

This is an OpenAI-compatible Text-to-Speech (TTS) API server built with FastAPI and `pocket-tts`. It functions as a drop-in replacement for OpenAI's audio endpoints, making it perfectly suited for applications like OpenWebUI.

## Prerequisites

* **Python 3**
* **uv**: For fast Python package and environment management.

## Setup & Installation

Follow these steps to create a virtual environment using `uv`, install the dependencies from your `requirements.txt`, and start the server. 

*(Note: Make sure `requirements.txt` and `openai_tts_server.py` are located in your working directory before running these commands).*

```bash
# Create the virtual environment
uv venv pocket_tts

# Navigate into the environment directory
cd pocket_tts

# Activate the environment (Linux/macOS)
# Note: On Windows, use `Scripts\activate` instead
source bin/activate


# Clone the repository
git clone https://github.com/officialorchid/OpenAI-Compatible-TTS-API-pocket-tts.git

# Navigate into the project directory
cd OpenAI-Compatible-TTS-API-pocket-tts

# Install the required dependencies
uv pip install -r requirements.txt

# Run the API server
uv run openai_tts_server.py

```

## Configuration

You can customize the server's behavior using the following environment variables:

* `PORT`: The port the server listens on (default: `8000`).
* `CACHE_DIR`: Directory where generated audio files are cached (default: `./tts_cache`).
* `VOICES_DIR`: Directory used to store and load custom voices (default: `./voices`).
* `MAX_CACHE`: Maximum number of files to retain in the cache before older files are deleted (default: `100`).

## Voices

The server seamlessly maps standard OpenAI voice names to their `pocket-tts` equivalents:

* **alloy** -> alba
* **echo** -> jean
* **fable** -> fantine
* **onyx** -> cosette
* **nova** -> eponine
* **shimmer** -> azelma

Additionally, the built-in voices `marius` and `javert` are available for use. You can also use custom voices by placing their `.wav` or `.safetensors` files inside the `VOICES_DIR`.

## Endpoints

* `GET /`: Returns basic API info and a list of available endpoints.
* `GET /health`: Health check detailing model load status and cached voices.
* `GET /v1/voices`: Lists all available OpenAI-mapped and built-in voices.
* `POST /v1/audio/speech`: The primary OpenAI-compatible endpoint for generating text-to-speech audio.
