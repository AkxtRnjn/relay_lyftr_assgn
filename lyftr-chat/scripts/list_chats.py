"""List sessions from the user's native database, for reopening older chats."""
import os
import sqlite3
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
url = os.getenv("DATABASE_URL") or dotenv_values(root / ".env").get("DATABASE_URL") or "sqlite:///./data/app.db"
if url == "sqlite:////data/app.db":
    url = "sqlite:///./data/app.db"
if not url.startswith("sqlite:///"):
    raise SystemExit("Expected a SQLite database URL.")
path = (root / "backend" / url.removeprefix("sqlite:///")).resolve()
if not path.is_file():
    raise SystemExit("No native chat database found at " + str(path))
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
    rows = db.execute("""
        SELECT m.session_id, m.content, m.created_at FROM messages AS m
        JOIN (SELECT session_id, MIN(id) AS first_id, MAX(id) AS last_id
              FROM messages WHERE role='user' GROUP BY session_id) AS sessions
        ON m.id=sessions.first_id ORDER BY sessions.last_id DESC
    """)
    for sid, content, created in rows:
        print(sid, created[:16], " ".join(content.split())[:72], sep="  ")
