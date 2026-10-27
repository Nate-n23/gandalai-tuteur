"""Réglages du tuteur, lus dans l'environnement (fichier .env chargé par systemd)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _bool(nom: str, defaut: bool) -> bool:
    valeur = os.environ.get(nom)
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "oui", "yes", "on"}


def _int(nom: str, defaut: int) -> int:
    valeur = os.environ.get(nom, "").strip()
    return int(valeur) if valeur.isdigit() else defaut


@dataclass(frozen=True)
class Reglages:
    # Mode démo : données fictives et réponses simulées, pour le frontend
    demo: bool
    # Stockage
    base_sqlite: str
    dossier_depots: str
    # Identité : en-tête transmis par le backend du portail (provisoire, en attendant IAM)
    entete_utilisateur: str
    # Limites
    max_upload_mo: int
    max_cours_par_etudiant: int
    max_documents_par_cours: int
    max_questions_heure: int
    max_caracteres_question: int
    # Services (utilisés à partir des lots B et C)
    ollama_url: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    llm_model: str
    embed_model: str
    num_ctx: int
    rag_version: int


@lru_cache
def reglages() -> Reglages:
    return Reglages(
        demo=_bool("TUTEUR_DEMO", False),
        base_sqlite=os.environ.get("TUTEUR_BASE", "/srv/gandal-ai/tuteur.sqlite3"),
        dossier_depots=os.environ.get("UPLOAD_DIR", "/srv/gandal-ai/depots"),
        entete_utilisateur=os.environ.get("TUTEUR_ENTETE_UTILISATEUR", "X-Utilisateur"),
        max_upload_mo=_int("MAX_UPLOAD_MB", 50),
        max_cours_par_etudiant=_int("MAX_COURS_PAR_ETUDIANT", 10),
        max_documents_par_cours=_int("MAX_DOCUMENTS_PAR_COURS", 10),
        max_questions_heure=_int("MAX_QUESTIONS_HEURE", 30),
        max_caracteres_question=_int("MAX_CARACTERES_QUESTION", 1000),
        ollama_url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
        qdrant_api_key=os.environ.get("QDRANT_API_KEY", ""),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "tuteur"),
        llm_model=os.environ.get("LLM_MODEL", "qwen3:14b"),
        embed_model=os.environ.get("EMBED_MODEL", "bge-m3"),
        num_ctx=_int("NUM_CTX", 8192),
        rag_version=_int("RAG_VERSION", 1),
    )
