"""Limites par étudiant : cours, fichiers par cours, questions par heure."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .config import reglages
from .erreurs import ErreurTuteur


def _il_y_a_une_heure() -> str:
    t = datetime.now(timezone.utc) - timedelta(hours=1)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def nb_cours(cx: sqlite3.Connection, etudiant: str) -> int:
    return cx.execute("SELECT COUNT(*) FROM cours WHERE etudiant = ?", (etudiant,)).fetchone()[0]


def nb_questions_heure(cx: sqlite3.Connection, etudiant: str) -> int:
    return cx.execute(
        "SELECT COUNT(*) FROM reponses WHERE etudiant = ? AND cree_le > ?",
        (etudiant, _il_y_a_une_heure()),
    ).fetchone()[0]


def verifier_cours(cx: sqlite3.Connection, etudiant: str) -> None:
    maxi = reglages().max_cours_par_etudiant
    if maxi and nb_cours(cx, etudiant) >= maxi:
        raise ErreurTuteur(
            429, "quota_atteint",
            f"Vous avez atteint la limite de {maxi} cours. Supprimez-en un pour en créer un autre.",
        )


def verifier_documents(cx: sqlite3.Connection, cours_id: str) -> None:
    maxi = reglages().max_documents_par_cours
    n = cx.execute("SELECT COUNT(*) FROM documents WHERE cours_id = ?", (cours_id,)).fetchone()[0]
    if maxi and n >= maxi:
        raise ErreurTuteur(
            429, "quota_atteint",
            f"Ce cours contient déjà {maxi} fichiers, le maximum.",
        )


def verifier_questions(cx: sqlite3.Connection, etudiant: str) -> None:
    maxi = reglages().max_questions_heure
    if not maxi:
        return
    if nb_questions_heure(cx, etudiant) < maxi:
        return
    # Délai avant que la plus ancienne question de l'heure ne sorte de la fenêtre
    plus_ancienne = cx.execute(
        "SELECT MIN(cree_le) FROM reponses WHERE etudiant = ? AND cree_le > ?",
        (etudiant, _il_y_a_une_heure()),
    ).fetchone()[0]
    t = datetime.fromisoformat(plus_ancienne.replace("Z", "+00:00")) + timedelta(hours=1)
    attente = max(1, int((t - datetime.now(timezone.utc)).total_seconds()) + 1)
    raise ErreurTuteur(
        429, "quota_atteint",
        f"Vous avez posé {maxi} questions dans l'heure. Réessayez dans {max(1, attente // 60)} min.",
        reessayer_apres=attente,
    )
