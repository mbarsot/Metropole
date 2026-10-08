import json

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

    def chat_stream(self, messages, *, temperature=0.2, max_tokens=900):
        """Yield text as Ollama generates it; close the response on cancellation."""
        if not self.model:
            self.choose_model()
        received_text = False
        completed = False
        try:
            with requests.post(
                self.url + "/api/chat",
                timeout=(5, self.timeout),
                stream=True,
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            ) as response:
                response.raise_for_status()
                # Avoid buffering short token events until a large chunk fills.
                for line in response.iter_lines(chunk_size=1):
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise OllamaError("Ollama returned an unexpected stream event.")
                    if data.get("error"):
                        raise OllamaError(str(data["error"]))
                    message = data.get("message", {})
                    if not isinstance(message, dict):
                        raise OllamaError("Ollama returned an invalid message.")
                    content = message.get("content", "")
                    if not isinstance(content, str):
                        raise OllamaError("Ollama returned invalid answer text.")
                    if content:
                        received_text = True
                        yield content
                    if data.get("done") is True:
                        completed = True
                        break
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(
                f"Ollama request failed at {self.url}/api/chat: {exc}. "
                "Check the host, network/VPN access, and that Ollama is listening."
            ) from exc
        if not completed:
            raise OllamaError("Ollama's response ended before completion. Please retry.")
        if not received_text:
            raise OllamaError("Ollama returned no answer text.")

    def chat(self, messages, *, temperature=0.2, max_tokens=900):
        # Loader and JSON API callers still need one complete answer.
        return "".join(self.chat_stream(
            messages, temperature=temperature, max_tokens=max_tokens
        )).strip()
