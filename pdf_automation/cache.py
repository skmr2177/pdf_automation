import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
  url TEXT PRIMARY KEY,
  etag TEXT,
  last_modified TEXT,
  content_hash TEXT,
  pdf_path TEXT,
  last_crawled INTEGER,
  status INTEGER
);
"""


@dataclass
class CacheEntry:
    url: str
    etag: Optional[str]
    last_modified: Optional[str]
    content_hash: Optional[str]
    pdf_path: Optional[str]
    last_crawled: Optional[int]
    status: Optional[int]


class Cache:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(DB_SCHEMA)
        self._conn.commit()

    def get(self, url: str) -> Optional[CacheEntry]:
        cur = self._conn.execute(
            "SELECT url, etag, last_modified, content_hash, pdf_path, last_crawled, status FROM pages WHERE url = ?",
            (url,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return CacheEntry(*row)

    def upsert(
        self,
        url: str,
        *,
        content_hash: Optional[str],
        pdf_path: Optional[str],
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        last_crawled: Optional[int] = None,
        status: Optional[int] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO pages (url, etag, last_modified, content_hash, pdf_path, last_crawled, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              etag=excluded.etag,
              last_modified=excluded.last_modified,
              content_hash=excluded.content_hash,
              pdf_path=excluded.pdf_path,
              last_crawled=excluded.last_crawled,
              status=excluded.status
            """,
            (url, etag, last_modified, content_hash, pdf_path, last_crawled, status),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

