"""
Persistence for base investment models (SQLite, stdlib only).

models          one row per model (metadata + pointer to the current version)
model_versions  immutable snapshots of a model's holdings; every save appends a version
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "data" / "models.db"
STATUSES = ("draft", "approved", "archived")

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_conn = _connect()


def init_db():
    with _lock, _conn:
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS models (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL UNIQUE,
                description   TEXT DEFAULT '',
                equity_target REAL,          -- intended equity share, e.g. 80 for an 80/20 model
                status        TEXT NOT NULL DEFAULT 'draft',
                sort_order    INTEGER DEFAULT 0,
                created_at    REAL NOT NULL,
                updated_at    REAL NOT NULL,
                updated_by    TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS model_versions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id    INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                version     INTEGER NOT NULL,
                holdings    TEXT NOT NULL,     -- JSON [{id, name, weight, fee}]
                note        TEXT DEFAULT '',
                created_at  REAL NOT NULL,
                created_by  TEXT DEFAULT '',
                UNIQUE(model_id, version)
            );
            """
        )
        cols = {r[1] for r in _conn.execute("PRAGMA table_info(model_versions)").fetchall()}
        if "config" not in cols:  # allocation-sheet models keep their full sheet (sections, settings) per version
            _conn.execute("ALTER TABLE model_versions ADD COLUMN config TEXT")


def equity_target_from_name(name: str) -> float | None:
    """'80/20' -> 80, '100' -> 100, 'מודל 60\\40' -> 60."""
    m = re.search(r"(\d{1,3})\s*[/\\\-]\s*(\d{1,3})", name or "")
    if m and int(m.group(1)) + int(m.group(2)) == 100:
        return float(m.group(1))
    m = re.fullmatch(r"\s*(\d{1,3})\s*%?\s*", name or "")
    if m and int(m.group(1)) <= 100:
        return float(m.group(1))
    return None


def _clean_holdings(holdings: list[dict]) -> list[dict]:
    out, seen = [], set()
    for h in holdings:
        hid = str(h.get("id") or "").strip()
        if not hid or hid in seen:
            continue
        seen.add(hid)
        fee = h.get("fee")
        out.append({
            "id": hid,
            "name": (h.get("name") or None),
            "weight": round(float(h.get("weight") or 0), 6),
            "fee": None if fee in (None, "") else float(fee),
        })
    return out


def _row_to_model(r: sqlite3.Row, version_row: sqlite3.Row | None) -> dict:
    holdings = json.loads(version_row["holdings"]) if version_row else []
    config = json.loads(version_row["config"]) if version_row and version_row["config"] else None
    return {
        "id": r["id"],
        "name": r["name"],
        "description": r["description"] or "",
        "equity_target": r["equity_target"],
        "status": r["status"],
        "sort_order": r["sort_order"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "updated_by": r["updated_by"] or "",
        "version": version_row["version"] if version_row else 0,
        "version_note": version_row["note"] if version_row else "",
        "holdings": holdings,
        "config": config,
        "kind": "allocation" if config else "list",
        "total_weight": round(sum(h["weight"] for h in holdings), 4),
    }


def _latest_version(model_id: int) -> sqlite3.Row | None:
    return _conn.execute(
        "SELECT * FROM model_versions WHERE model_id=? ORDER BY version DESC LIMIT 1", (model_id,)
    ).fetchone()


def list_models(include_archived: bool = False) -> list[dict]:
    with _lock:
        q = "SELECT * FROM models" + ("" if include_archived else " WHERE status != 'archived'")
        rows = _conn.execute(q + " ORDER BY sort_order, COALESCE(equity_target, -1) DESC, name").fetchall()
        return [_row_to_model(r, _latest_version(r["id"])) for r in rows]


def get_model(model_id: int) -> dict | None:
    with _lock:
        r = _conn.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
        if not r:
            return None
        m = _row_to_model(r, _latest_version(model_id))
        m["versions"] = [
            {"version": v["version"], "note": v["note"], "created_at": v["created_at"], "created_by": v["created_by"],
             "count": len(json.loads(v["holdings"]))}
            for v in _conn.execute(
                "SELECT * FROM model_versions WHERE model_id=? ORDER BY version DESC", (model_id,)
            ).fetchall()
        ]
        return m


def get_model_by_name(name: str) -> dict | None:
    with _lock:
        r = _conn.execute("SELECT id FROM models WHERE name=?", (name,)).fetchone()
    return get_model(r["id"]) if r else None


def get_version(model_id: int, version: int) -> dict | None:
    with _lock:
        v = _conn.execute(
            "SELECT * FROM model_versions WHERE model_id=? AND version=?", (model_id, version)
        ).fetchone()
        if not v:
            return None
        return {"version": v["version"], "note": v["note"], "created_at": v["created_at"],
                "created_by": v["created_by"], "holdings": json.loads(v["holdings"]),
                "config": json.loads(v["config"]) if v["config"] else None}


def create_model(name: str, holdings: list[dict], description: str = "", equity_target: float | None = None,
                 status: str = "draft", user: str = "", note: str = "יצירת מודל", config: dict | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("שם המודל ריק")
    if status not in STATUSES:
        raise ValueError("סטטוס לא חוקי")
    now = time.time()
    if equity_target is None:
        equity_target = equity_target_from_name(name)
    with _lock, _conn:
        if _conn.execute("SELECT 1 FROM models WHERE name=?", (name,)).fetchone():
            raise ValueError(f"מודל בשם '{name}' כבר קיים")
        order = (_conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM models").fetchone()[0] or 0) + 1
        cur = _conn.execute(
            "INSERT INTO models(name, description, equity_target, status, sort_order, created_at, updated_at, updated_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, description, equity_target, status, order, now, now, user),
        )
        mid = cur.lastrowid
        _conn.execute(
            "INSERT INTO model_versions(model_id, version, holdings, note, created_at, created_by, config) VALUES (?,?,?,?,?,?,?)",
            (mid, 1, json.dumps(_clean_holdings(holdings), ensure_ascii=False), note, now, user, _cfg(config)),
        )
    return get_model(mid)


def _cfg(config: dict | None) -> str | None:
    return json.dumps(config, ensure_ascii=False, sort_keys=True) if config else None


def update_model(model_id: int, *, holdings: list[dict] | None = None, name: str | None = None,
                 description: str | None = None, equity_target: Any = "__keep__", status: str | None = None,
                 user: str = "", note: str = "", config: Any = "__keep__") -> dict:
    now = time.time()
    with _lock, _conn:
        r = _conn.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
        if not r:
            raise KeyError(model_id)
        if name is not None and name.strip() != r["name"]:
            if _conn.execute("SELECT 1 FROM models WHERE name=? AND id!=?", (name.strip(), model_id)).fetchone():
                raise ValueError(f"מודל בשם '{name}' כבר קיים")
        if status is not None and status not in STATUSES:
            raise ValueError("סטטוס לא חוקי")
        _conn.execute(
            "UPDATE models SET name=?, description=?, equity_target=?, status=?, updated_at=?, updated_by=? WHERE id=?",
            (
                (name or r["name"]).strip(),
                r["description"] if description is None else description,
                r["equity_target"] if equity_target == "__keep__" else equity_target,
                status or r["status"],
                now, user or r["updated_by"], model_id,
            ),
        )
        if holdings is not None or config != "__keep__":
            latest = _conn.execute(
                "SELECT version, holdings, config FROM model_versions WHERE model_id=? ORDER BY version DESC LIMIT 1", (model_id,)
            ).fetchone()
            new_h = _clean_holdings(holdings) if holdings is not None else (json.loads(latest["holdings"]) if latest else [])
            new_c = (latest["config"] if latest else None) if config == "__keep__" else _cfg(config)
            # Only append a version when the holdings or the allocation sheet actually changed
            if not latest or json.loads(latest["holdings"]) != new_h or (latest["config"] or None) != new_c:
                _conn.execute(
                    "INSERT INTO model_versions(model_id, version, holdings, note, created_at, created_by, config) VALUES (?,?,?,?,?,?,?)",
                    (model_id, (latest["version"] if latest else 0) + 1, json.dumps(new_h, ensure_ascii=False), note, now, user, new_c),
                )
    return get_model(model_id)


def archive_model(model_id: int, user: str = "") -> dict:
    return update_model(model_id, status="archived", user=user)


def is_empty() -> bool:
    with _lock:
        return _conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 0


def delete_model(model_id: int) -> bool:
    """Permanently delete a model and its whole version history (cannot be undone)."""
    with _lock, _conn:
        if not _conn.execute("SELECT 1 FROM models WHERE id=?", (model_id,)).fetchone():
            return False
        _conn.execute("DELETE FROM model_versions WHERE model_id=?", (model_id,))
        _conn.execute("DELETE FROM models WHERE id=?", (model_id,))
    return True
