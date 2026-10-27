"""Mode démo (TUTEUR_DEMO=1) : même contrat que le vrai tuteur, sans modèle ni GPU.

- Les fichiers déposés passent seuls de « en_attente » à « en_lecture » puis « pret ».
- Les questions reçoivent une réponse fictive, envoyée en flux comme la vraie.

Cas particuliers, pour que le frontend puisse tester tous les états :
- un fichier dont le nom contient « illisible » finit en « erreur » ;
- un fichier dont le nom contient « scan » finit « pret » avec un avertissement ;
- une question qui contient « hors cours » reçoit une réponse « hors_cours ».
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import AsyncIterator

from .base import maintenant

ATTENTE_S = 3      # durée simulée en file d'attente
LECTURE_S = 6      # durée simulée de lecture


def _age_s(horodatage: str | None) -> float:
    if not horodatage:
        return 0.0
    t = datetime.fromisoformat(horodatage.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - t).total_seconds()


def avancer_documents(cx: sqlite3.Connection) -> None:
    """Fait progresser les fichiers selon le temps écoulé, un seul en lecture à la fois."""
    for d in cx.execute("SELECT * FROM documents WHERE statut = 'en_lecture'").fetchall():
        if _age_s(d["debut_lecture"]) < LECTURE_S:
            continue
        nom = d["nom"].lower()
        if "illisible" in nom:
            cx.execute(
                "UPDATE documents SET statut='erreur', fin_lecture=?, message=? WHERE id=?",
                (maintenant(), "Le fichier n'a pas pu être lu. Vérifiez qu'il s'ouvre correctement, puis déposez-le à nouveau.", d["id"]),
            )
        else:
            pages = max(1, d["taille"] // 60_000)
            avert = (
                "Peu de texte a été reconnu sur ce fichier : les réponses risquent d'être incomplètes."
                if "scan" in nom else None
            )
            cx.execute(
                "UPDATE documents SET statut='pret', fin_lecture=?, pages=?, avertissement=? WHERE id=?",
                (maintenant(), pages, avert, d["id"]),
            )
    en_cours = cx.execute("SELECT COUNT(*) FROM documents WHERE statut = 'en_lecture'").fetchone()[0]
    if en_cours:
        return
    suivant = cx.execute(
        "SELECT id, depose_le FROM documents WHERE statut = 'en_attente' ORDER BY depose_le, id LIMIT 1"
    ).fetchone()
    if suivant and _age_s(suivant["depose_le"]) >= ATTENTE_S:
        cx.execute(
            "UPDATE documents SET statut='en_lecture', debut_lecture=? WHERE id=?",
            (maintenant(), suivant["id"]),
        )


async def reponse_simulee(question: str, documents: list[sqlite3.Row]) -> AsyncIterator[tuple[str, dict]]:
    """Produit les événements (nom, données) d'une réponse fictive."""
    if "hors cours" in question.lower():
        morceaux = ["Je ne trouve pas la réponse dans ce cours. ", "Essayez de reformuler votre question."]
        for m in morceaux:
            await asyncio.sleep(0.3)
            yield "texte", {"t": m}
        yield "sources", {"sources": []}
        yield "fin_statut", {"statut": "hors_cours"}
        return

    doc = documents[0]
    sources = [
        {
            "n": 1, "document_id": doc["id"], "nom": doc["nom"], "page": 12,
            "section": "2.1 Nombre dérivé",
            "extrait": "On appelle nombre dérivé de f en a la limite, si elle existe et est finie, "
                       "du taux d'accroissement (f(a+h) - f(a)) / h quand h tend vers 0.",
        },
        {
            "n": 2, "document_id": doc["id"], "nom": doc["nom"], "page": 14,
            "section": "2.3 Interprétation graphique",
            "extrait": "Le nombre dérivé f'(a) est le coefficient directeur de la tangente "
                       "à la courbe de f au point d'abscisse a.",
        },
    ]
    texte = (
        "**Réponse de démonstration.** "
        "Le nombre dérivé de f en a est la limite du taux d'accroissement de f entre a et a + h, "
        "quand h tend vers 0 [1]. "
        "Graphiquement, c'est le coefficient directeur de la tangente à la courbe en a [2].\n\n"
        "- Si cette limite n'existe pas, f n'est pas dérivable en a.\n"
        "- Ce texte est fictif : il sert seulement à tester l'affichage."
    )
    for i in range(0, len(texte), 24):
        await asyncio.sleep(0.05)
        yield "texte", {"t": texte[i:i + 24]}
    yield "sources", {"sources": sources}
    yield "fin_statut", {"statut": "ok"}
