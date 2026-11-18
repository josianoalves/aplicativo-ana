import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dados"
DEFAULT = {
    "keywords": "", "limit": 30, "select": 3, "variants": 2, "duration": 25,
    "times": dict(research="08:05", analyze="08:20", select="08:30", script="08:40", video="09:00"),
}


class Store:
    def __init__(self, folder=DATA):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "radar.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(id TEXT, at TEXT, data TEXT, PRIMARY KEY(id,at));
                CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY, at TEXT, stage TEXT, status TEXT, message TEXT);
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO config VALUES (?,?)", (key, json.dumps(value)))

    def rows(self, table):
        query = {"products": "SELECT data FROM products", "videos": "SELECT data FROM videos"}[table]
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(query)]

    def save(self, table, records, snapshot=None):
        query = {
            "products": "INSERT OR REPLACE INTO products VALUES (?,?)",
            "videos": "INSERT OR REPLACE INTO videos VALUES (?,?)",
        }[table]
        rows = [(str(item["id"]), json.dumps(item, ensure_ascii=False)) for item in records]
        with self.connect() as db:
            db.executemany(query, rows)
            if snapshot:
                db.executemany("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                               [(key, snapshot, payload) for key, payload in rows])

    def log(self, stage, status, message):
        with self.connect() as db:
            db.execute("INSERT INTO logs(at,stage,status,message) VALUES (?,?,?,?)",
                       (datetime.now().astimezone().isoformat(timespec="seconds"), stage, status, message))

    def logs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 150")]

    def backup(self):
        folder = self.folder / "backups"
        folder.mkdir(exist_ok=True)
        target = folder / datetime.now().strftime("radar-%Y%m%d-%H%M%S-%f.sqlite3")
        with self.connect() as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        return target
