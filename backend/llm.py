import json
import requests
from threading import Lock

from .config import Config


class LocalLlamaError(RuntimeError):
    """Raised when the local Llama runtime request fails."""


class OllamaModelManager:
    """Load the configured model once and keep it resident in Ollama."""

    def __init__(self):
        self._lock = Lock()
        self._loaded = False

    def load(self) -> None:
        """Preload the model without generating a user-facing response."""
        with self._lock:
            if self._loaded:
                return

            print("Loading LLaMA model...", flush=True)
            try:
                running = requests.get(f"{Config.OLLAMA_BASE_URL}/api/ps", timeout=10)
                running.raise_for_status()
                loaded_models = running.json().get("models", [])
                if not any(model.get("name") == Config.LLAMA_MODEL for model in loaded_models):
                    response = requests.post(
                        f"{Config.OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": Config.LLAMA_MODEL,
                            "prompt": "",
                            "stream": False,
                            "keep_alive": -1,
                            "options": {"num_predict": 0},
                        },
                        timeout=120,
                    )
                    response.raise_for_status()
            except requests.exceptions.RequestException as exc:
                raise LocalLlamaError(
                    "Could not preload the local LLaMA model. Start Ollama and make sure "
                    f"`{Config.LLAMA_MODEL}` is installed. Details: {exc}"
                ) from exc

            self._loaded = True
            print("LLaMA model loaded successfully.", flush=True)

    def chat(self, messages: list) -> str:
        """Run inference and return the complete response for compatibility."""
        return "".join(self.stream_chat(messages))

    def stream_chat(self, messages: list):
        """Yield response text chunks from Ollama as they are generated."""
        if not self._loaded:
            raise LocalLlamaError("LLaMA was not loaded during backend startup.")

        payload = {
            "model": Config.LLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {
                "num_predict": Config.LLAMA_MAX_TOKENS,
                "temperature": Config.LLAMA_TEMPERATURE,
            },
        }

        try:
            response = requests.post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                stream=True,
                timeout=(10, 120),
            )
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                data = json.loads(line)
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break
        except requests.exceptions.Timeout as exc:
            raise LocalLlamaError("The local Llama model timed out. Please try again.") from exc
        except requests.exceptions.RequestException as exc:
            raise LocalLlamaError(
                "Could not reach Ollama. Start Ollama and make sure the model is installed "
                f"with `ollama pull {Config.LLAMA_MODEL}`."
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LocalLlamaError("Unexpected response format from the local Llama runtime.") from exc


model_manager = OllamaModelManager()


def load_llama_model() -> None:
    """Initialize the shared Ollama model manager during Flask startup."""
    model_manager.load()


def build_llm_messages(context_rows) -> list:
    """FR8: build the model prompt from the complete multi-turn session context."""
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful, accurate, and concise AI assistant. "
                "Continue the current session naturally across multiple turns and topics. "
                "Provide clear, structured responses. If you are unsure, say so honestly."
            ),
        }
    ] + [{"role": row["role"], "content": row["content"]} for row in context_rows]


def query_llama(messages: list) -> str:
    """FR9: reuse the startup-loaded local Ollama model for this conversation."""
    return model_manager.chat(messages)
