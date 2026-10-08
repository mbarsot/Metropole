# Metropole

A datacenter knowledge assistant with two applications: a command-line loader,
and a conversational assistant available in the terminal and through Flask.
Procedure files stay in a local SQLite knowledge repository. Relevant excerpts
are retrieved with SQLite FTS5 and sent to your existing Ollama server with each
question. This is retrieval-augmented generation, not model training.

## Install

Python 3.11+ with SQLite FTS5 is required (validated with Python 3.12).
From the checkout directory:

```sh
bash scripts/setup.sh
source .venv/bin/activate
metropole --help
```

The setup script installs pinned dependencies and runs the automated suite using
a local Ollama HTTP fixture. It needs no datacenter documents or Ollama access.
The fixture verifies integration behavior, not the accuracy of a real model.

## Ollama connection

Default: `http://10.3.81.142:11434`. Choose a different host at startup with
`--host`, or use `--prompt-host` for an interactive prompt. Both accept a bare
hostname, `hostname:port`, or an HTTP(S) URL. The host is an Ollama server,
independent of the address on which the Flask application listens.

```sh
metropole doctor --host 10.3.81.142
metropole chat --prompt-host
metropole serve --host 10.3.81.142 --model YOUR_INSTALLED_MODEL
```

If no model is selected, Metropole queries `/api/tags` and chooses the first
installed model whose name does not suggest an embedding-only model. Select your
preferred lightweight chat model with `--model`; nothing is downloaded to the
server automatically. `doctor` checks `/api/tags` and performs a real `/api/chat`
request. Make sure Ollama listens on a reachable interface and the firewall
permits access from the application machine.

Every subcommand also accepts `--db` and `--timeout`. Environment defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_HOST` | `10.3.81.142` | Existing Ollama server |
| `OLLAMA_MODEL` | auto-select | Installed chat model name |
| `OLLAMA_TIMEOUT` | `120` | Response timeout in seconds |
| `METROPOLE_DB` | `data/knowledge.sqlite3` | Local repository path |

The default database path is relative to the current working directory. Run from
the checkout or set an absolute path so the loader and chat use the same database.
No API key is required for a standard local Ollama server.

## Loader

Export the OneNote notes to UTF-8 `.txt` or `.md`. Native `.one`, PDF, images, and
OCR are not supported in this first version. Word `.docx` files are supported,
including paragraphs and table cells in document order. Text in drawings, embedded
objects, headers, and footers is not extracted.

Tagged notes preserve their labels:

```text
<restore-files-from-avamar>
Your approved restoration procedure goes here.
</restore-files-from-avamar>
------
Free-form notes about another procedure go here.
```

Separators must be lines containing six or more hyphens. Untagged blocks, including
text surrounding tagged blocks, receive a descriptive tag inferred by Ollama.
The loader prints all assigned tags for review. Original procedure text is retained;
the model generates labels only. `.docx` tags are derived from the filename:
`Restore Files From Avamar.docx` becomes `restore-files-from-avamar`.

```sh
# Interactive loader: enter paths, /list, or /quit
metropole load --prompt-host

# Import one or more files or recursively import a directory
metropole load /path/to/OneNote-Notes.txt /path/to/documents/

# Offline fallback: label untagged sections from their first line, without AI
metropole load --offline-tags examples/notes.txt

# Inspect the loaded labels and source files
metropole list
```

Quote paths containing spaces. Fully tagged text and `.docx` imports do not need
Ollama. AI inference sends up to the first 6,000 characters of an untagged section
to the selected server. Large procedures are split into overlapping search excerpts.

Reimporting the same absolute source path atomically replaces its old procedures
and excerpts. Different file paths count as different sources. Failed or empty
imports retain previous entries; batch imports continue other files and exit
nonzero if any fail. Imports are additive across different sources. Renamed or
deleted source files are not automatically removed from the repository.

`examples/notes.txt` contains clearly labelled demonstration text. Do not use it
as an actual operating procedure or mix examples into your real knowledge database.

## Conversational assistant

```sh
metropole chat --host 10.3.81.142
metropole serve --host 10.3.81.142 --port 5000
```

In terminal chat, `/reset` starts a new conversation and `/quit` exits. In the web
interface, use **New conversation**. Follow-up questions reuse recent user turns
for retrieval. Responses include numbered references, and the web interface lets
you expand each source excerpt. Conversation history stays in terminal memory or
the browser tab; it is not stored in the database.

Flask binds to loopback by default. This is a development interface without user
authentication. For multi-user deployment, add authentication and run behind a
production WSGI server and appropriate network controls. Bind to another interface
only intentionally with `--bind`. The Ollama host is selected by the operator at
startup, not by individual browser requests.

Endpoints:

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Local application/database health; does not claim Ollama readiness |
| `GET /api/status` | Check Ollama model discovery |
| `POST /api/chat` | JSON `question` and optional `history` of user/assistant messages |

The assistant is prompted to answer from the retrieved procedures and cite them.
If no excerpts match, it returns a clear no-match message without calling Ollama.
Retrieval uses keyword search rather than embeddings; try product and task names
when results are weak. Model answers and inferred tags still require human review.
Metropole never executes operating commands. It sends retrieved procedure text
to your selected Ollama server; use an approved server for confidential material.

## Development and cloud environment

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

Tests exercise mixed-note parsing, real Word files, source replacement/rollback,
chunking, retrieval, follow-up conversations, CLI workflows, error handling, and
Flask routes against a local HTTP implementation of the Ollama protocol.

Use the existing checkout in an isolated cloud task; no Git worktree is necessary.
Dependencies and the SQLite file persist on disk, but servers must be restarted.
Run `metropole doctor` on a machine with access to the datacenter network to check
the actual model. A private IP may require the cloud environment's VPN/network
configuration. Do not bypass the configured proxy or install a separate VPN client.

The knowledge database and imported confidential files are excluded from Git.
Keep originals and back up the SQLite repository separately. The actual OneNote
and Word documents can be loaded once supplied; they are not included here.
