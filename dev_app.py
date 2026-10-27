"""Application autonome, en attendant le code de GANDAL-AI.

    TUTEUR_DEMO=1 TUTEUR_BASE=./tuteur.sqlite3 UPLOAD_DIR=./depots \
        uvicorn dev_app:app --port 8090

Dans GANDAL-AI, seule la ligne installer(app) est à ajouter dans service/app.py.
"""
from fastapi import FastAPI

from service.tuteur import installer
from service.tuteur.config import reglages

app = FastAPI(title="GANDAL-AI (tuteur, mode autonome)")
installer(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "demo": reglages().demo}
