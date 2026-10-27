"""Schémas des requêtes et réponses, tels que décrits dans le contrat d'API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Statut = Literal["en_attente", "en_lecture", "pret", "erreur"]


class Document(BaseModel):
    id: str
    nom: str
    pages: Optional[int] = None
    statut: Statut
    position: Optional[int] = None
    avertissement: Optional[str] = None
    message: Optional[str] = None
    depose_le: str


class Cours(BaseModel):
    id: str
    titre: str
    cree_le: str
    documents: list[Document] = []


class Quota(BaseModel):
    cours: int
    cours_max: int
    documents_max_par_cours: int
    taille_max_mo: int
    questions_heure: int
    questions_heure_max: int


class ListeCours(BaseModel):
    quota: Quota
    cours: list[Cours]


class NouveauCours(BaseModel):
    titre: str = Field(min_length=1, max_length=120)


class DepotAccepte(BaseModel):
    id: str
    statut: Statut
    position: Optional[int] = None


class Question(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: Optional[str] = None


class Avis(BaseModel):
    utile: bool
    commentaire: Optional[str] = Field(default=None, max_length=1000)


class Source(BaseModel):
    n: int
    document_id: str
    nom: str
    page: Optional[int] = None
    section: Optional[str] = None
    extrait: str
