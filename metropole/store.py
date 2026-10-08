import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .ingest import chunk_text


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS procedures (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL,
                    section INTEGER NOT NULL, tag TEXT NOT NULL, text TEXT NOT NULL,
                    UNIQUE(source, section)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                    tag, text, procedure_id UNINDEXED, source UNINDEXED,
                    tokenize='unicode61 remove_diacritics 2'
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def replace_source(self, source, procedures):
        # One transaction per source: a failed import cannot leave partial knowledge.
        with self.connect() as db:
            db.execute("DELETE FROM chunks WHERE source = ?", (source,))
            db.execute("DELETE FROM procedures WHERE source = ?", (source,))
            for procedure in procedures:
                row = db.execute(
                    "INSERT INTO procedures(source,section,tag,text) VALUES(?,?,?,?)",
                    (source, procedure.section, procedure.tag, procedure.text),
                )
                for chunk in chunk_text(procedure.text):
                    db.execute("INSERT INTO chunks(tag,text,procedure_id,source) VALUES(?,?,?,?)",
                               (procedure.tag, chunk, row.lastrowid, source))
        return len(procedures)

    def list_procedures(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,tag,source,section,length(text) AS characters FROM procedures ORDER BY source,section"
            )]

    def search(self, question, limit=5):
        tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", question.lower(), re.UNICODE)))[:40]
        stopwords = {"the", "a", "an", "is", "are", "to", "of", "and", "or", "how", "do", "i", "it", "can", "you", "what", "with", "for", "please", "that", "this", "in"}
        tokens = [t for t in tokens if t not in stopwords and len(t) > 1]
        if not tokens:
            return []
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with self.connect() as db:
            rows = db.execute(
                "SELECT tag,text,source,procedure_id,bm25(chunks,4.0,1.0) AS score "
                "FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?", (expression, limit)
            )
            return [dict(row) for row in rows]
