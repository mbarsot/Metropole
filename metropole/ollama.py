import requests

from .config import Settings


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, settings: Settings):
        self.url = settings.base_url
        self.model = settings.model
        self.timeout = settings.timeout

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(
                method, self.url + path, timeout=(5, self.timeout), **kwargs
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(
                f"Ollama request failed at {self.url}{path}: {exc}. "
                "Check the host, network/VPN access, and that Ollama is listening."
            ) from exc
        if not isinstance(data, dict):
            raise OllamaError("Ollama returned an unexpected response.")
        if data.get("error"):
            raise OllamaError(str(data["error"]))
        return data

    def models(self):
        data = self._request("GET", "/api/tags")
        return [item["name"] for item in data.get("models", []) if item.get("name")]

    def choose_model(self):
        models = self.models()
        if not models:
            raise OllamaError("No models are installed on this Ollama server.")
        if self.model:
            if self.model not in models and self.model + ":latest" not in models:
                raise OllamaError(f"Model {self.model!r} is not installed. Available: {', '.join(models)}")
        else:
            # Preserve the server's order; prefer a chat model over embedding-only models.
            candidates = [m for m in models if not any(x in m.lower() for x in ("embed", "bge", "minilm"))]
            if not candidates:
                raise OllamaError("Only embedding models were found. Select an installed chat model.")
            self.model = candidates[0]
        return self.model

    def chat(self, messages, *, temperature=0.2, max_tokens=900):
        if not self.model:
            self.choose_model()
        data = self._request("POST", "/api/chat", json={
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        })
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned no answer text.")
        return content.strip()
