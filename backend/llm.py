import requests

from .config import Config


class LocalLlamaError(RuntimeError):
    """Raised when the local Llama runtime request fails."""


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
    """FR9: send the complete conversation to the local Ollama Llama model."""
    payload = {
        "model": Config.LLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 1024, "temperature": 0.7},
    }

    try:
        # Ollama runs locally 
        response = requests.post(
            f"{Config.OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        # Return the generated local Llama text for the frontend to display.
        return data["message"]["content"]
    except requests.exceptions.Timeout as exc:
        raise LocalLlamaError("The local Llama model timed out. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        raise LocalLlamaError(
            "Could not reach Ollama. Start Ollama and make sure the model is installed "
            f"with `ollama pull {Config.LLAMA_MODEL}`."
        ) from exc
    except (KeyError, IndexError) as exc:
        raise LocalLlamaError("Unexpected response format from the local Llama runtime.") from exc
