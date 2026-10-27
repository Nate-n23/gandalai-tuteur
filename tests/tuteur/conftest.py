import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTEUR_DEMO", "1")
    monkeypatch.setenv("TUTEUR_BASE", str(tmp_path / "tuteur.sqlite3"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "depots"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_COURS_PAR_ETUDIANT", "3")
    monkeypatch.setenv("MAX_QUESTIONS_HEURE", "2")

    from service.tuteur import config, demo, installer
    config.reglages.cache_clear()
    monkeypatch.setattr(demo, "ATTENTE_S", 0)
    monkeypatch.setattr(demo, "LECTURE_S", 0)

    app = FastAPI()
    installer(app)
    with TestClient(app) as c:
        yield c
    config.reglages.cache_clear()


ETU1 = {"X-Utilisateur": "etu1"}
ETU2 = {"X-Utilisateur": "etu2"}


def creer_cours(client, titre="Analyse 1", entetes=ETU1):
    r = client.post("/tuteur/cours", json={"titre": titre}, headers=entetes)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def deposer(client, cours_id, nom="cours.pdf", contenu=b"%PDF-1.4 test", entetes=ETU1, usage="true"):
    return client.post(
        f"/tuteur/cours/{cours_id}/documents",
        files={"fichier": (nom, contenu, "application/pdf")},
        data={"usage_personnel": usage},
        headers=entetes,
    )


def attendre_pret(client, cours_id, entetes=ETU1):
    # Mode démo à délais nuls : chaque lecture fait avancer la file d'un cran.
    for _ in range(10):
        docs = client.get(f"/tuteur/cours/{cours_id}", headers=entetes).json()["documents"]
        if all(d["statut"] in ("pret", "erreur") for d in docs):
            return docs
    raise AssertionError(docs)


def evenements(texte):
    sortie = []
    for bloc in texte.strip().split("\n\n"):
        lignes = dict(l.split(": ", 1) for l in bloc.splitlines())
        sortie.append((lignes["event"], lignes["data"]))
    return sortie
