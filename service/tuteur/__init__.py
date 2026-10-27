"""Module tuteur de GANDAL-AI.

Pour le brancher dans l'application existante (service/app.py) :

    from service.tuteur import installer
    installer(app)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .base import initialiser
from .erreurs import ErreurTuteur, gerer_erreur_tuteur, gerer_validation
from .routes import router


def installer(app: FastAPI) -> None:
    initialiser()
    app.include_router(router)
    app.add_exception_handler(ErreurTuteur, gerer_erreur_tuteur)
    app.add_exception_handler(RequestValidationError, gerer_validation)
