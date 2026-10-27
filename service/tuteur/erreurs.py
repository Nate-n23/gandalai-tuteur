"""Erreurs du contrat d'API : toujours {"code": ..., "message": ...}, message prêt à afficher."""
from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErreurTuteur(Exception):
    def __init__(self, http: int, code: str, message: str, **extra):
        super().__init__(message)
        self.http = http
        self.code = code
        self.message = message
        self.extra = extra


def introuvable() -> ErreurTuteur:
    # Même réponse pour « n'existe pas » et « appartient à un autre étudiant » :
    # on ne révèle jamais l'existence des cours des autres.
    return ErreurTuteur(404, "introuvable", "Ce cours ou ce fichier est introuvable.")


async def gerer_erreur_tuteur(_: Request, exc: ErreurTuteur) -> JSONResponse:
    corps = {"code": exc.code, "message": exc.message, **exc.extra}
    entetes = {}
    if "reessayer_apres" in exc.extra:
        entetes["Retry-After"] = str(exc.extra["reessayer_apres"])
    return JSONResponse(corps, status_code=exc.http, headers=entetes)


async def gerer_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Seulement pour les routes du tuteur ; le reste de GANDAL-AI garde le format FastAPI.
    if not request.url.path.startswith("/tuteur"):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    return JSONResponse(
        {"code": "requete_invalide", "message": "La requête est incomplète ou mal formée."},
        status_code=422,
    )
