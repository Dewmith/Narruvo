"""SQLite library. The owning GUI thread performs short transactions only."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from voiceleaf.domain import LibraryDocument, PdfInfo, ReadingProgress


class Library:
    """SQLite library using short transactions on its owning GUI thread.

    Content hashes identify documents. Removing a record never removes the
    original PDF at its referenced path.
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.connection.close()
            raise RuntimeError("This library was created by a newer VoiceLeaf version.")
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL,
                    page_count INTEGER NOT NULL, last_opened TEXT NOT NULL,
                    view_page INTEGER NOT NULL DEFAULT 0, chunk_index INTEGER NOT NULL DEFAULT 0,
                    position_ms INTEGER NOT NULL DEFAULT 0, active_voice TEXT NOT NULL DEFAULT 'af_heart',
                    active_rate REAL NOT NULL DEFAULT 1.0, preferred_voice TEXT NOT NULL DEFAULT 'af_heart',
                    preferred_rate REAL NOT NULL DEFAULT 1.0, chunk_hash TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0
                )
            """)
            self.connection.execute("PRAGMA user_version=1")

    def upsert(self, info: PdfInfo, defaults: ReadingProgress | None = None) -> ReadingProgress:
        """Store document metadata and return progress for its content identity."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            # A changed file at an existing path is a new reading session.
            self.connection.execute("DELETE FROM documents WHERE path=? AND document_id<>?", (info.path, info.document_id))
            exists = self.get(info.document_id)
            self.connection.execute("""
                INSERT INTO documents(document_id,path,title,page_count,last_opened) VALUES(?,?,?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET path=excluded.path,title=excluded.title,
                page_count=excluded.page_count,last_opened=excluded.last_opened
            """, (info.document_id, info.path, info.title, info.page_count, now))
            if not exists and defaults:
                self.save_progress(info.document_id, defaults)
        return self.get(info.document_id).progress

    @staticmethod
    def _record(row: sqlite3.Row) -> LibraryDocument:
        progress = ReadingProgress(**{key: row[key] for key in ReadingProgress.__dataclass_fields__})
        progress.completed = bool(progress.completed)
        return LibraryDocument(row["document_id"], row["path"], row["title"], row["page_count"], row["last_opened"], progress)

    def get(self, document_id: str) -> LibraryDocument | None:
        row = self.connection.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
        return self._record(row) if row else None

    def recent(self) -> list[LibraryDocument]:
        return [self._record(row) for row in self.connection.execute("SELECT * FROM documents ORDER BY last_opened DESC")]

    def save_progress(self, document_id: str, progress: ReadingProgress) -> None:
        values = {name: getattr(progress, name) for name in ReadingProgress.__dataclass_fields__}
        assignment = ",".join(f"{name}=?" for name in values)
        with self.connection:
            self.connection.execute(f"UPDATE documents SET {assignment} WHERE document_id=?", (*values.values(), document_id))

    def remove(self, document_id: str) -> None:
        """Delete library metadata while leaving the original PDF in place."""
        with self.connection:
            self.connection.execute("DELETE FROM documents WHERE document_id=?", (document_id,))

    def close(self) -> None:
        self.connection.close()
