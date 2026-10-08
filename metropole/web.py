from flask import Flask, jsonify, render_template, request

from .chat import Chat
from .config import Settings
from .ollama import Ollama, OllamaError
from .store import Store


def create_app(settings=None, *, client=None):
    settings = settings or Settings.from_env()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    store = Store(settings.db_path)
    client = client or Ollama(settings)
    chat = Chat(store, client)

    @app.get("/")
    def index():
        return render_template("index.html", host=settings.base_url,
                               model=client.model or "auto-select", count=len(store.list_procedures()))

    @app.get("/health")
    def health():
        return jsonify(status="ok", procedures=len(store.list_procedures()))

    @app.get("/api/status")
    def status():
        try:
            model = client.choose_model()
            return jsonify(status="ok", model=model, host=settings.base_url,
                           procedures=len(store.list_procedures()))
        except OllamaError as exc:
            return jsonify(error=str(exc)), 502

    @app.post("/api/chat")
    def ask():
        # Browser requests must originate from this UI, preventing cross-site use
        # of a local Ollama-backed service. Non-browser CLI clients need no Origin.
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="Cross-origin requests are not allowed."), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("question"), str):
            return jsonify(error="Supply a JSON object with a question string."), 400
        history = data.get("history", [])
        if not isinstance(history, list) or len(history) > 12:
            return jsonify(error="History must contain at most 12 messages."), 400
        for item in history:
            if (not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}
                    or not isinstance(item.get("content"), str) or len(item["content"]) > 8000):
                return jsonify(error="Invalid conversation history."), 400
        try:
            return jsonify(chat.ask(data["question"], history))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except OllamaError as exc:
            return jsonify(error=str(exc)), 502

    return app
