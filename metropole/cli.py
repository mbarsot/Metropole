import argparse
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from .chat import Chat
from .config import Settings
from .ingest import read_source
from .ollama import Ollama, OllamaError
from .store import Store


def connection_options(parser):
    defaults = Settings.from_env()
    parser.add_argument("--host", default=defaults.host, help="Ollama host or URL (default: 10.3.81.142)")
    parser.add_argument("--model", default=defaults.model, help="Installed Ollama chat model; otherwise auto-select")
    parser.add_argument("--db", default=defaults.database, help="SQLite knowledge repository path")
    parser.add_argument("--timeout", default=defaults.timeout, type=float, help="Ollama response timeout in seconds")
    parser.add_argument("--prompt-host", action="store_true", help="Ask for an Ollama host at startup")


def build_parser():
    parser = argparse.ArgumentParser(description="Metropole datacenter knowledge assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load", help="Import notes or .docx files; no paths opens interactive loader")
    connection_options(load)
    load.add_argument("paths", nargs="*")
    load.add_argument("--offline-tags", action="store_true", help="Label untagged text from its first line instead of AI inference")
    chat = commands.add_parser("chat", help="Interactive terminal conversation")
    connection_options(chat)
    serve = commands.add_parser("serve", help="Start the Flask chat interface")
    connection_options(serve)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5000)
    for command, description in [("doctor", "Check repository and Ollama connection"), ("list", "List loaded procedures")]:
        sub = commands.add_parser(command, help=description)
        connection_options(sub)
    return parser


def import_paths(paths, store, client, offline=False):
    files = []
    for name in paths:
        path = Path(name).expanduser()
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.is_file() and p.suffix.lower() in {".docx", ".txt", ".md"} and not p.name.startswith("~$"))
        else:
            files.append(path)
    if not files:
        raise ValueError("No supported files found.")
    failed = False
    for path in dict.fromkeys(files):
        try:
            procedures = read_source(path, client, offline)
            if not procedures:
                raise ValueError("No text found; existing entries were retained.")
            count = store.replace_source(str(path.resolve()), procedures)
            print(f"Loaded {count} procedures from {path.name}")
            for procedure in procedures:
                print(f"  <{procedure.tag}> ({len(procedure.text)} characters)")
        except Exception as exc:
            # Continue independent documents; explicitly return a failing exit
            # status if any import failed (including corrupt Word documents).
            print(f"Could not load {path}: {exc}", file=sys.stderr)
            failed = True
    return not failed


def interactive_load(args, store, client):
    print("Enter a file or directory path (quote paths with spaces). Commands: /list, /quit")
    success = True
    while True:
        try:
            line = input("load> ").strip()
        except EOFError:
            break
        if line == "/quit":
            break
        if line == "/list":
            print_procedures(store)
        elif line:
            success = import_paths(shlex.split(line), store, client, args.offline_tags) and success
    return 0 if success else 1


def print_procedures(store):
    items = store.list_procedures()
    print(f"{len(items)} procedures")
    for item in items:
        print(f"<{item['tag']}> — {item['source']} (section {item['section']})")


def interactive_chat(store, client):
    print(f"Ollama model: {client.choose_model()}")
    print("Ask questions. Commands: /reset, /quit")
    chat = Chat(store, client)
    history = []
    while True:
        try:
            question = input("you> ").strip()
        except EOFError:
            break
        if question == "/quit":
            break
        if question == "/reset":
            history.clear()
            print("Conversation cleared.")
            continue
        if not question:
            continue
        try:
            result = chat.ask(question, history)
            print(f"\nMetropole> {result['answer']}\n")
            for source in result["sources"]:
                print(f"[{source['number']}] <{source['tag']}> — {source['source']}")
            history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"][:8000]}])
            history = history[-12:]
        except (ValueError, OllamaError) as exc:
            print(str(exc), file=sys.stderr)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        settings = Settings(args.host, args.model, args.db, args.timeout)
        if args.prompt_host:
            settings = replace(settings, host=input(f"Ollama host [{settings.host}]: ").strip() or settings.host)
        if settings.timeout <= 0:
            raise ValueError("Timeout must be positive.")
        client = Ollama(settings)
        store = Store(settings.db_path)
        if args.command == "load":
            if args.paths:
                return 0 if import_paths(args.paths, store, client, args.offline_tags) else 1
            return interactive_load(args, store, client)
        if args.command == "list":
            print_procedures(store)
            return 0
        if args.command == "doctor":
            print(f"Repository: {settings.db_path.resolve()} ({len(store.list_procedures())} procedures)")
            print(f"Ollama: {settings.base_url}")
            print(f"Chat model: {client.choose_model()}")
            print("Model response: " + client.chat([{"role": "user", "content": "Reply with OK."}], max_tokens=16))
            return 0
        if args.command == "chat":
            return interactive_chat(store, client)
        if args.command == "serve":
            from .web import create_app
            create_app(settings, client=client).run(host=args.bind, port=args.port, debug=False)
            return 0
    except (ValueError, OSError, OllamaError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
