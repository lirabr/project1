from __future__ import annotations

import json
import sqlite3
from typing import Any

import numpy as np

from desk.regime import situation_vector


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS situation_vecs (
            episode_id INTEGER PRIMARY KEY,
            symbol TEXT,
            regime TEXT,
            vec_json TEXT NOT NULL,
            lesson TEXT
        )
        """
    )
    conn.commit()


def upsert(conn: sqlite3.Connection, episode_id: int, symbol: str, regime: str, row: dict[str, Any], lesson: str | None) -> None:
    _ensure(conn)
    vec = situation_vector(row)
    conn.execute(
        """
        INSERT INTO situation_vecs (episode_id, symbol, regime, vec_json, lesson)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(episode_id) DO UPDATE SET
            regime=excluded.regime, vec_json=excluded.vec_json, lesson=excluded.lesson
        """,
        (episode_id, symbol, regime, json.dumps(vec.tolist()), lesson or ""),
    )
    conn.commit()


def similar(conn: sqlite3.Connection, row: dict[str, Any], k: int = 3) -> list[dict[str, Any]]:
    _ensure(conn)
    q = situation_vector(row)
    stored = conn.execute("SELECT * FROM situation_vecs WHERE lesson IS NOT NULL AND lesson != ''").fetchall()
    if not stored:
        return []
    scored = []
    for s in stored:
        v = np.asarray(json.loads(s["vec_json"]), dtype=float)
        sim = float(np.dot(q, v)) if v.shape == q.shape else 0.0
        scored.append((sim, dict(s)))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sim, row_ in scored[:k]:
        row_["similarity"] = sim
        out.append(row_)
    return out
