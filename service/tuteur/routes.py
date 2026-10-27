"""Les 9 routes du contrat d'API du tuteur (GET /health reste celle de GANDAL-AI)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import StreamingResponse

from . import demo, quotas
from .base import connexion, maintenant, nouvel_id, position_dans_file
from .config import reglages
from .erreurs import ErreurTuteur, introuvable
from .identite import etudiant_courant
from .schemas import (Avis, Cours, DepotAccepte, Document, ListeCours, NouveauCours,
                      Question, Quota)

router = APIRouter(prefix="/tuteur", tags=["tuteur"])

FORMATS = {".pdf": "PDF", ".pptx": "PowerPoint", ".docx": "Word"}


# ---------- lectures ----------

def _document(cx: sqlite3.Connection, d: sqlite3.Row) -> Document:
    return Document(
        id=d["id"], nom=d["nom"], pages=d["pages"], statut=d["statut"],
        position=position_dans_file(cx, d["id"]), avertissement=d["avertissement"],
        message=d["message"], depose_le=d["depose_le"],
    )


def _cours(cx: sqlite3.Connection, c: sqlite3.Row) -> Cours:
    docs = cx.execute(
        "SELECT * FROM documents WHERE cours_id = ? ORDER BY depose_le, id", (c["id"],)
    ).fetchall()
    return Cours(id=c["id"], titre=c["titre"], cree_le=c["cree_le"],
                 documents=[_document(cx, d) for d in docs])


def _cours_de(cx: sqlite3.Connection, cours_id: str, etudiant: str) -> sqlite3.Row:
    c = cx.execute(
        "SELECT * FROM cours WHERE id = ? AND etudiant = ?", (cours_id, etudiant)
    ).fetchone()
    if c is None:
        raise introuvable()
    return c


def _avancer(cx: sqlite3.Connection) -> None:
    if reglages().demo:
        demo.avancer_documents(cx)


# ---------- cours ----------

@router.get("/cours", response_model=ListeCours)
def lister_cours(etudiant: str = Depends(etudiant_courant)) -> ListeCours:
    r = reglages()
    with connexion() as cx:
        _avancer(cx)
        lignes = cx.execute(
            "SELECT * FROM cours WHERE etudiant = ? ORDER BY cree_le, id", (etudiant,)
        ).fetchall()
        return ListeCours(
            quota=Quota(
                cours=len(lignes), cours_max=r.max_cours_par_etudiant,
                documents_max_par_cours=r.max_documents_par_cours, taille_max_mo=r.max_upload_mo,
                questions_heure=quotas.nb_questions_heure(cx, etudiant),
                questions_heure_max=r.max_questions_heure,
            ),
            cours=[_cours(cx, c) for c in lignes],
        )


@router.post("/cours", response_model=Cours, status_code=201)
def creer_cours(corps: NouveauCours, etudiant: str = Depends(etudiant_courant)) -> Cours:
    titre = corps.titre.strip()
    if not titre:
        raise ErreurTuteur(400, "titre_requis", "Donnez un titre au cours.")
    with connexion() as cx:
        quotas.verifier_cours(cx, etudiant)
        cours_id = nouvel_id("c")
        cx.execute(
            "INSERT INTO cours (id, etudiant, titre, cree_le) VALUES (?, ?, ?, ?)",
            (cours_id, etudiant, titre, maintenant()),
        )
        return _cours(cx, _cours_de(cx, cours_id, etudiant))


@router.get("/cours/{cours_id}", response_model=Cours)
def lire_cours(cours_id: str, etudiant: str = Depends(etudiant_courant)) -> Cours:
    with connexion() as cx:
        _avancer(cx)
        return _cours(cx, _cours_de(cx, cours_id, etudiant))


@router.delete("/cours/{cours_id}", status_code=204)
def supprimer_cours(cours_id: str, etudiant: str = Depends(etudiant_courant)) -> Response:
    with connexion() as cx:
        _cours_de(cx, cours_id, etudiant)
        chemins = [d["chemin"] for d in cx.execute(
            "SELECT chemin FROM documents WHERE cours_id = ?", (cours_id,))]
        # Les documents, conversations, réponses et avis suivent (ON DELETE CASCADE).
        cx.execute("DELETE FROM cours WHERE id = ?", (cours_id,))
    for chemin in chemins:
        _effacer(chemin)
    # Lot B : effacer aussi les vecteurs du cours dans Qdrant.
    return Response(status_code=204)


# ---------- documents ----------

@router.post("/cours/{cours_id}/documents", response_model=DepotAccepte, status_code=202)
async def deposer_document(
    cours_id: str,
    fichier: UploadFile = File(...),
    usage_personnel: str = Form(""),
    etudiant: str = Depends(etudiant_courant),
) -> DepotAccepte:
    r = reglages()
    if usage_personnel.strip().lower() not in {"true", "1", "oui", "on"}:
        raise ErreurTuteur(400, "usage_personnel_requis",
                           "Cochez la case « Ce document est pour mon usage personnel ».")
    nom = os.path.basename(fichier.filename or "").strip()
    extension = os.path.splitext(nom)[1].lower()
    if extension not in FORMATS:
        raise ErreurTuteur(400, "format_refuse",
                           "Ce format n'est pas accepté. Formats acceptés : PDF, PowerPoint, Word.")
    with connexion() as cx:
        _cours_de(cx, cours_id, etudiant)
        quotas.verifier_documents(cx, cours_id)

    document_id = nouvel_id("d")
    dossier = os.path.join(r.dossier_depots, etudiant)
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, document_id + extension)
    limite = r.max_upload_mo * 1024 * 1024
    empreinte, taille = hashlib.sha256(), 0
    try:
        with open(chemin, "wb") as sortie:
            while bloc := await fichier.read(1024 * 1024):
                taille += len(bloc)
                if taille > limite:
                    raise ErreurTuteur(413, "fichier_trop_gros",
                                       f"Le fichier dépasse {r.max_upload_mo} Mo.")
                empreinte.update(bloc)
                sortie.write(bloc)
        if taille == 0:
            raise ErreurTuteur(400, "fichier_vide", "Le fichier est vide.")
    except BaseException:
        _effacer(chemin)
        raise

    with connexion() as cx:
        cx.execute(
            "INSERT INTO documents (id, cours_id, etudiant, nom, chemin, taille, sha256, statut, depose_le) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'en_attente', ?)",
            (document_id, cours_id, etudiant, nom, chemin, taille, empreinte.hexdigest(), maintenant()),
        )
        return DepotAccepte(id=document_id, statut="en_attente",
                            position=position_dans_file(cx, document_id))


@router.delete("/documents/{document_id}", status_code=204)
def supprimer_document(document_id: str, etudiant: str = Depends(etudiant_courant)) -> Response:
    with connexion() as cx:
        d = cx.execute(
            "SELECT chemin FROM documents WHERE id = ? AND etudiant = ?", (document_id, etudiant)
        ).fetchone()
        if d is None:
            raise introuvable()
        cx.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    _effacer(d["chemin"])
    # Lot B : effacer aussi les vecteurs du document dans Qdrant.
    return Response(status_code=204)


def _effacer(chemin: str) -> None:
    try:
        os.remove(chemin)
    except FileNotFoundError:
        pass


# ---------- questions ----------

def _sse(nom: str, donnees: dict) -> str:
    return f"event: {nom}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


@router.post("/cours/{cours_id}/questions")
async def poser_question(
    cours_id: str, corps: Question, etudiant: str = Depends(etudiant_courant)
) -> StreamingResponse:
    r = reglages()
    question = corps.question.strip()
    if not question:
        raise ErreurTuteur(400, "question_vide", "Écrivez une question.")
    if len(question) > r.max_caracteres_question:
        raise ErreurTuteur(400, "question_trop_longue",
                           f"La question dépasse {r.max_caracteres_question} caractères.")

    with connexion() as cx:
        _avancer(cx)
        _cours_de(cx, cours_id, etudiant)
        prets = cx.execute(
            "SELECT * FROM documents WHERE cours_id = ? AND statut = 'pret' ORDER BY depose_le",
            (cours_id,),
        ).fetchall()
        if not prets:
            raise ErreurTuteur(409, "aucun_document_pret",
                               "Aucun fichier de ce cours n'est encore prêt. Patientez pendant la lecture.")
        if not r.demo:
            # Lot C : recherche dans Qdrant puis réponse d'Ollama.
            raise ErreurTuteur(503, "service_indisponible",
                               "Le tuteur est momentanément indisponible.")
        quotas.verifier_questions(cx, etudiant)

        conversation_id = corps.conversation_id
        if conversation_id:
            ok = cx.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND cours_id = ? AND etudiant = ?",
                (conversation_id, cours_id, etudiant),
            ).fetchone()
            if not ok:
                raise introuvable()
        else:
            conversation_id = nouvel_id("v")
            cx.execute(
                "INSERT INTO conversations (id, cours_id, etudiant, cree_le) VALUES (?, ?, ?, ?)",
                (conversation_id, cours_id, etudiant, maintenant()),
            )
        reponse_id = nouvel_id("r")
        cx.execute(
            "INSERT INTO reponses (id, conversation_id, etudiant, question, statut, cree_le) "
            "VALUES (?, ?, ?, ?, 'en_cours', ?)",
            (reponse_id, conversation_id, etudiant, question, maintenant()),
        )

    async def flux() -> AsyncIterator[str]:
        debut = time.monotonic()
        texte, sources, statut = [], [], "erreur"
        yield _sse("debut", {"conversation_id": conversation_id, "reponse_id": reponse_id})
        try:
            async for nom, donnees in demo.reponse_simulee(question, prets):
                if nom == "texte":
                    texte.append(donnees["t"])
                    yield _sse("texte", donnees)
                elif nom == "sources":
                    sources = donnees["sources"]
                    yield _sse("sources", donnees)
                elif nom == "fin_statut":
                    statut = donnees["statut"]
            duree = int((time.monotonic() - debut) * 1000)
            yield _sse("fin", {"statut": statut, "duree_ms": duree})
        except asyncio.CancelledError:
            statut = "interrompue"   # l'étudiant a cliqué « Arrêter » ou fermé la page
            raise
        except Exception:
            statut = "erreur"
            yield _sse("erreur", {"code": "service_indisponible",
                                  "message": "La réponse a été interrompue. Réessayez."})
        finally:
            with connexion() as cx:
                cx.execute(
                    "UPDATE reponses SET texte = ?, sources = ?, statut = ?, duree_ms = ? WHERE id = ?",
                    ("".join(texte), json.dumps(sources, ensure_ascii=False), statut,
                     int((time.monotonic() - debut) * 1000), reponse_id),
                )

    return StreamingResponse(
        flux(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- avis ----------

@router.post("/reponses/{reponse_id}/avis", status_code=204)
def donner_avis(reponse_id: str, corps: Avis, etudiant: str = Depends(etudiant_courant)) -> Response:
    with connexion() as cx:
        ok = cx.execute(
            "SELECT 1 FROM reponses WHERE id = ? AND etudiant = ?", (reponse_id, etudiant)
        ).fetchone()
        if not ok:
            raise introuvable()
        cx.execute(
            "INSERT INTO avis (reponse_id, etudiant, utile, commentaire, cree_le) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(reponse_id) DO UPDATE SET utile = excluded.utile, "
            "commentaire = excluded.commentaire, cree_le = excluded.cree_le",
            (reponse_id, etudiant, int(corps.utile), corps.commentaire, maintenant()),
        )
    return Response(status_code=204)
