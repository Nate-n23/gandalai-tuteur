"""Qui est l'étudiant ?

Provisoire : le backend du portail vérifie la session avec IAM, puis transmet
l'identifiant dans un en-tête (par défaut X-Utilisateur). Seul le reverse proxy
peut joindre le port 8090, donc l'en-tête ne vient pas du navigateur.
À remplacer par la vérification décidée avec IAM (jeton JWT, en-tête signé).
"""
from __future__ import annotations

import re

from fastapi import Request

from .config import reglages
from .erreurs import ErreurTuteur

_FORMAT = re.compile(r"^[A-Za-z0-9._@-]{1,128}$")


def etudiant_courant(request: Request) -> str:
    valeur = request.headers.get(reglages().entete_utilisateur, "").strip()
    if not valeur or not _FORMAT.match(valeur):
        raise ErreurTuteur(401, "non_authentifie", "Votre session a expiré. Reconnectez-vous.")
    return valeur
