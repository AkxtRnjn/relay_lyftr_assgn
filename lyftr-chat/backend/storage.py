import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, url):
        if not url.startswith("sqlite:///"):
            raise ValueError("DATABASE_URL must start with sqlite:///")
        self.path = Path(url.removeprefix("sqlite:///"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, system_prompt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS session_order ON messages(session_id, id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def history(self, sid):
        with self.connect() as db:
            prompt = db.execute("SELECT system_prompt FROM sessions WHERE id=?", (sid,)).fetchone()
            rows = db.execute("SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (sid,))
            messages = [{"role": role, "content": content, **({"metadata": json.loads(meta)} if meta else {})}
                        for role, content, meta in rows]
        return prompt[0] if prompt else None, messages

    def save(self, sid, prompt, message, reply, metadata):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET system_prompt=excluded.system_prompt",
                       (sid, prompt))
            db.executemany("INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
                           [(sid, "user", message, None, now), (sid, "assistant", reply, json.dumps(metadata), now)])
