"""Base SQLite du tuteur : cours, documents (et file d'attente), conversations, réponses, avis.

Une connexion par opération : simple, et sans risque entre l'API et le worker,
qui tournent dans deux processus différents (mode WAL).
"""
from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .config import reglages

SCHEMA = """
CREATE TABLE IF NOT EXISTS cours (
    id        TEXT PRIMARY KEY,
    etudiant  TEXT NOT NULL,
    titre     TEXT NOT NULL,
    cree_le   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cours_etudiant ON cours(etudiant);

CREATE TABLE IF NOT EXISTS documents (
    id             TEXT PRIMARY KEY,
    cours_id       TEXT NOT NULL REFERENCES cours(id) ON DELETE CASCADE,
    etudiant       TEXT NOT NULL,
    nom            TEXT NOT NULL,
    chemin         TEXT NOT NULL,
    taille         INTEGER NOT NULL,
    sha256         TEXT NOT NULL,
    statut         TEXT NOT NULL DEFAULT 'en_attente',
    pages          INTEGER,
    avertissement  TEXT,
    message        TEXT,
    depose_le      TEXT NOT NULL,
    debut_lecture  TEXT,
    fin_lecture    TEXT
);
CREATE INDEX IF NOT EXISTS documents_cours ON documents(cours_id);
CREATE INDEX IF NOT EXISTS documents_file ON documents(statut, depose_le);

CREATE TABLE IF NOT EXISTS conversations (
    id        TEXT PRIMARY KEY,
    cours_id  TEXT NOT NULL REFERENCES cours(id) ON DELETE CASCADE,
    etudiant  TEXT NOT NULL,
    cree_le   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reponses (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    etudiant         TEXT NOT NULL,
    question         TEXT NOT NULL,
    texte            TEXT,
    sources          TEXT,
    statut           TEXT,
    duree_ms         INTEGER,
    cree_le          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reponses_quota ON reponses(etudiant, cree_le);

CREATE TABLE IF NOT EXISTS avis (
    reponse_id   TEXT PRIMARY KEY REFERENCES reponses(id) ON DELETE CASCADE,
    etudiant     TEXT NOT NULL,
    utile        INTEGER NOT NULL,
    commentaire  TEXT,
    cree_le      TEXT NOT NULL
);
"""


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def nouvel_id(prefixe: str) -> str:
    return f"{prefixe}_{secrets.token_hex(4)}"


@contextmanager
def connexion() -> Iterator[sqlite3.Connection]:
    chemin = reglages().base_sqlite
    os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
    cx = sqlite3.connect(chemin, timeout=10)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA foreign_keys = ON")
    cx.execute("PRAGMA journal_mode = WAL")
    try:
        yield cx
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()


def initialiser() -> None:
    with connexion() as cx:
        cx.executescript(SCHEMA)


def position_dans_file(cx: sqlite3.Connection, document_id: str) -> int | None:
    """Position (1 = le prochain) d'un document en attente, toutes files confondues."""
    ligne = cx.execute(
        "SELECT statut, depose_le FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    if ligne is None or ligne["statut"] != "en_attente":
        return None
    avant = cx.execute(
        "SELECT COUNT(*) FROM documents WHERE statut = 'en_attente' "
        "AND (depose_le < ? OR (depose_le = ? AND id < ?))",
        (ligne["depose_le"], ligne["depose_le"], document_id),
    ).fetchone()[0]
    return avant + 1
