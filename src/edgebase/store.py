from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Edge, FileFacts, Symbol


EDGEBASE_DIR = ".edgebase"
DB_NAME = "index.sqlite3"


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.dir = self.root / EDGEBASE_DIR
        self.path = self.dir / DB_NAME

    def exists(self) -> bool:
        return self.path.exists()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            self.migrate(conn)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              sha TEXT NOT NULL,
              language TEXT NOT NULL,
              module TEXT NOT NULL,
              loc INTEGER NOT NULL,
              is_test INTEGER NOT NULL,
              commit_sha TEXT NOT NULL,
              indexed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS symbols (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,
              file_path TEXT NOT NULL,
              line INTEGER NOT NULL,
              end_line INTEGER NOT NULL,
              signature TEXT NOT NULL,
              exported INTEGER NOT NULL,
              extractor TEXT NOT NULL,
              confidence REAL NOT NULL,
              commit_sha TEXT NOT NULL,
              UNIQUE(file_path, kind, name, line)
            );

            CREATE TABLE IF NOT EXISTS edges (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              src_type TEXT NOT NULL,
              src_key TEXT NOT NULL,
              rel TEXT NOT NULL,
              dst_type TEXT NOT NULL,
              dst_key TEXT NOT NULL,
              file_path TEXT NOT NULL,
              line INTEGER NOT NULL,
              extractor TEXT NOT NULL,
              confidence REAL NOT NULL,
              commit_sha TEXT NOT NULL,
              freshness TEXT NOT NULL,
              UNIQUE(src_type, src_key, rel, dst_type, dst_key, file_path, line)
            );

            CREATE TABLE IF NOT EXISTS file_metrics (
              file_path TEXT PRIMARY KEY,
              churn_count INTEGER NOT NULL,
              last_commit TEXT NOT NULL,
              owner TEXT NOT NULL,
              authors_json TEXT NOT NULL,
              recent_commits_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_type, src_key);
            CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_type, dst_key);
            CREATE INDEX IF NOT EXISTS idx_edges_file ON edges(file_path);
            """
        )

    def reset(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                DELETE FROM meta;
                DELETE FROM files;
                DELETE FROM symbols;
                DELETE FROM edges;
                DELETE FROM file_metrics;
                """
            )

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else ""

    def delete_file(self, rel_path: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
            conn.execute("DELETE FROM symbols WHERE file_path = ?", (rel_path,))
            conn.execute("DELETE FROM edges WHERE file_path = ?", (rel_path,))
            conn.execute("DELETE FROM edges WHERE src_key LIKE ?", (f"{rel_path}#%",))
            conn.execute("DELETE FROM edges WHERE dst_key = ?", (rel_path,))
            conn.execute("DELETE FROM file_metrics WHERE file_path = ?", (rel_path,))

    def delete_edges_by_extractor(self, extractor: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM edges WHERE extractor = ?", (extractor,))

    def upsert_file(self, facts: FileFacts, sha: str, commit_sha: str, indexed_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO files(path, sha, language, module, loc, is_test, commit_sha, indexed_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  sha=excluded.sha,
                  language=excluded.language,
                  module=excluded.module,
                  loc=excluded.loc,
                  is_test=excluded.is_test,
                  commit_sha=excluded.commit_sha,
                  indexed_at=excluded.indexed_at
                """,
                (
                    facts.path,
                    sha,
                    facts.language,
                    facts.module,
                    facts.loc,
                    1 if facts.is_test else 0,
                    commit_sha,
                    indexed_at,
                ),
            )
            conn.execute("DELETE FROM symbols WHERE file_path = ?", (facts.path,))
            conn.execute("DELETE FROM edges WHERE file_path = ?", (facts.path,))
            for symbol in facts.symbols:
                self._insert_symbol(conn, symbol, commit_sha)
            for edge in facts.edges:
                self._insert_edge(conn, edge, commit_sha, "fresh")

    def add_edge(self, edge: Edge, commit_sha: str, freshness: str = "fresh") -> None:
        with self.connect() as conn:
            self._insert_edge(conn, edge, commit_sha, freshness)

    def upsert_metrics(
        self,
        file_path: str,
        churn_count: int,
        last_commit: str,
        owner: str,
        authors: dict[str, int],
        recent_commits: list[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO file_metrics(
                  file_path, churn_count, last_commit, owner, authors_json, recent_commits_json
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                  churn_count=excluded.churn_count,
                  last_commit=excluded.last_commit,
                  owner=excluded.owner,
                  authors_json=excluded.authors_json,
                  recent_commits_json=excluded.recent_commits_json
                """,
                (
                    file_path,
                    churn_count,
                    last_commit,
                    owner,
                    json.dumps(authors, sort_keys=True),
                    json.dumps(recent_commits),
                ),
            )

    def load_graph(self) -> dict[str, list[sqlite3.Row]]:
        with self.connect() as conn:
            return {
                "files": list(conn.execute("SELECT * FROM files ORDER BY path")),
                "symbols": list(conn.execute("SELECT * FROM symbols ORDER BY file_path, line")),
                "edges": list(conn.execute("SELECT * FROM edges ORDER BY file_path, line")),
                "metrics": list(conn.execute("SELECT * FROM file_metrics ORDER BY file_path")),
            }

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            return {
                "files": int(conn.execute("SELECT count(*) FROM files").fetchone()[0]),
                "symbols": int(conn.execute("SELECT count(*) FROM symbols").fetchone()[0]),
                "edges": int(conn.execute("SELECT count(*) FROM edges").fetchone()[0]),
            }

    def _insert_symbol(self, conn: sqlite3.Connection, symbol: Symbol, commit_sha: str) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO symbols(
              name, kind, file_path, line, end_line, signature, exported, extractor, confidence, commit_sha
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol.name,
                symbol.kind,
                symbol.file_path,
                symbol.line,
                symbol.end_line,
                symbol.signature,
                1 if symbol.exported else 0,
                symbol.extractor,
                symbol.confidence,
                commit_sha,
            ),
        )

    def _insert_edge(
        self, conn: sqlite3.Connection, edge: Edge, commit_sha: str, freshness: str
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO edges(
              src_type, src_key, rel, dst_type, dst_key, file_path, line,
              extractor, confidence, commit_sha, freshness
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge.src_type,
                edge.src_key,
                edge.rel,
                edge.dst_type,
                edge.dst_key,
                edge.file_path,
                edge.line,
                edge.extractor,
                edge.confidence,
                commit_sha,
                freshness,
            ),
        )
