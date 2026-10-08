import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from werkzeug.exceptions import RequestEntityTooLarge

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from .chat import Chat
from .config import Settings
from .ingest import read_source
from .ollama import Ollama, OllamaError
from .store import Store


def create_app(settings=None, *, client=None):
    settings = settings or Settings.from_env()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
    store = Store(settings.db_path)
    client = client or Ollama(settings)
    chat = Chat(store, client)

    @app.before_request
    def protect_requests():
        if request.path == "/api/chat":
            request.max_content_length = 64 * 1024
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Cross-origin requests are not allowed."), 403

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        limit = "64 KB" if request.path == "/api/chat" else "100 MB"
        return jsonify(error=f"Request exceeds the {limit} limit. Upload fewer or smaller files."), 413

    @app.get("/api/knowledge")
    def knowledge():
        files = {}
        procedures = store.list_procedures()
        for item in procedures:
            source = item["source"]
            file = files.setdefault(source, {
                "source": source, "filename": source.replace("\\", "/").rsplit("/", 1)[-1],
                "skills": [],
            })
            file["skills"].append({"tag": item["tag"], "section": item["section"],
                                   "characters": item["characters"]})
        return jsonify(files=list(files.values()), procedures=len(procedures))

    @app.post("/api/load")
    def load():
        uploads = request.files.getlist("files")
        if not uploads:
            return jsonify(error="Choose at least one .txt, .md, or .docx file."), 400
        if len(uploads) > 200:
            return jsonify(error="Upload at most 200 files at a time."), 400
        offline = request.form.get("offline_tags", "false")
        if offline not in {"true", "false"}:
            return jsonify(error="offline_tags must be true or false."), 400

        # Flask closes request-owned upload streams when returning a response.
        # Stage our own temporary copies before starting progress streaming.
        staging = TemporaryDirectory(prefix="metropole-upload-")
        staged = []
        try:
            for index, upload in enumerate(uploads):
                name = (upload.filename or "").replace("\\", "/")
                try:
                    relative = PurePosixPath(name)
                    if (not name or relative.is_absolute() or ".." in relative.parts
                            or ":" in name or "\x00" in name or not relative.name):
                        raise ValueError("Invalid upload filename.")
                    if relative.suffix.lower() not in {".txt", ".md", ".docx"}:
                        raise ValueError("Unsupported file. Choose .txt, .md, or .docx.")
                    folder = Path(staging.name) / str(index)
                    folder.mkdir()
                    path = folder / relative.name
                    upload.save(path)
                    staged.append((name, relative.as_posix(), path, None))
                except Exception as exc:
                    staged.append((name, None, None, str(exc)))
        except BaseException:
            staging.cleanup()
            raise

        def events():
            loaded = failed = 0
            try:
                for name, relative, path, error in staged:
                    yield json.dumps({"type": "loading", "filename": name}) + "\n"
                    try:
                        if error:
                            raise ValueError(error)
                        try:
                            procedures = read_source(path, client, fallback=offline == "true")
                        finally:
                            path.unlink(missing_ok=True)
                        if not procedures:
                            raise ValueError("No text found; existing entries were retained.")
                        source = "upload://" + relative
                        procedures = [replace(item, source=source) for item in procedures]
                        count = store.replace_source(source, procedures)
                        loaded += 1
                        yield json.dumps({"type": "loaded", "filename": name, "procedures": count,
                                          "skills": [item.tag for item in procedures]}) + "\n"
                    except Exception as exc:
                        failed += 1
                        yield json.dumps({"type": "failed", "filename": name, "error": str(exc)}) + "\n"
                yield json.dumps({"type": "done", "loaded": loaded, "failed": failed}) + "\n"
            finally:
                staging.cleanup()

        response = Response(stream_with_context(events()), mimetype="application/x-ndjson",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        response.call_on_close(staging.cleanup)
        return response

    @app.get("/")
    def index():
        return render_template("index.html", host=settings.base_url,
                               model=client.model or "auto-select", timeout=settings.timeout,
                               count=len(store.list_procedures()))

    @app.get("/health")
    def health():
        return jsonify(status="ok", procedures=len(store.list_procedures()))

    @app.get("/api/status")
    def status():
        try:
            model = client.choose_model()
            return jsonify(status="ok", model=model, host=settings.base_url, timeout=settings.timeout,
                           procedures=len(store.list_procedures()))
        except OllamaError as exc:
            return jsonify(error=str(exc)), 502

    @app.post("/api/chat")
    def ask():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("question"), str):
            return jsonify(error="Supply a JSON object with a question string."), 400
        if not isinstance(data.get("stream", False), bool):
            return jsonify(error="stream must be a boolean."), 400
        history = data.get("history", [])
        if not isinstance(history, list) or len(history) > 12:
            return jsonify(error="History must contain at most 12 messages."), 400
        for item in history:
            if (not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}
                    or not isinstance(item.get("content"), str) or len(item["content"]) > 8000):
                return jsonify(error="Invalid conversation history."), 400
        try:
            if data.get("stream", False):
                # Validate before sending headers. Once streaming starts, failures
                # are reported as terminal error events rather than HTTP statuses.
                prepared = chat.prepare(data["question"], history)

                def events():
                    try:
                        with closing(chat.stream(data["question"], history, prepared=prepared)) as stream:
                            for event in stream:
                                yield json.dumps(event) + "\n"
                    except OllamaError as exc:
                        yield json.dumps({"type": "error", "error": str(exc)}) + "\n"

                return Response(stream_with_context(events()), mimetype="application/x-ndjson",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
            return jsonify(chat.ask(data["question"], history))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except OllamaError as exc:
            return jsonify(error=str(exc)), 502

    return app
