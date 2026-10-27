import json

from .conftest import ETU1, ETU2, attendre_pret, creer_cours, deposer, evenements


def test_sans_identite_401(client):
    r = client.get("/tuteur/cours")
    assert r.status_code == 401
    assert r.json()["code"] == "non_authentifie"


def test_liste_vide_et_quota(client):
    r = client.get("/tuteur/cours", headers=ETU1)
    assert r.status_code == 200
    corps = r.json()
    assert corps["cours"] == []
    assert corps["quota"]["cours"] == 0
    assert corps["quota"]["cours_max"] == 3
    assert corps["quota"]["taille_max_mo"] == 1


def test_creer_et_lire_cours(client):
    cours_id = creer_cours(client)
    assert cours_id.startswith("c_")
    r = client.get(f"/tuteur/cours/{cours_id}", headers=ETU1)
    assert r.json()["titre"] == "Analyse 1"
    assert r.json()["documents"] == []


def test_quota_cours(client):
    for i in range(3):
        creer_cours(client, f"Cours {i}")
    r = client.post("/tuteur/cours", json={"titre": "Un de trop"}, headers=ETU1)
    assert r.status_code == 429
    assert r.json()["code"] == "quota_atteint"


def test_depot_et_lecture(client):
    cours_id = creer_cours(client)
    r = deposer(client, cours_id)
    assert r.status_code == 202
    assert r.json()["statut"] == "en_attente"
    assert r.json()["position"] == 1
    docs = attendre_pret(client, cours_id)
    assert docs[0]["statut"] == "pret"
    assert docs[0]["pages"] >= 1


def test_depot_refus(client):
    cours_id = creer_cours(client)
    assert deposer(client, cours_id, nom="notes.txt").json()["code"] == "format_refuse"
    assert deposer(client, cours_id, usage="").json()["code"] == "usage_personnel_requis"
    trop_gros = deposer(client, cours_id, contenu=b"x" * (1024 * 1024 + 1))
    assert trop_gros.status_code == 413
    assert trop_gros.json()["code"] == "fichier_trop_gros"


def test_demo_erreur_et_avertissement(client):
    cours_id = creer_cours(client)
    deposer(client, cours_id, nom="illisible.pdf")
    deposer(client, cours_id, nom="cours-scan.pdf")
    docs = {d["nom"]: d for d in attendre_pret(client, cours_id)}
    assert docs["illisible.pdf"]["statut"] == "erreur"
    assert docs["illisible.pdf"]["message"]
    assert docs["cours-scan.pdf"]["statut"] == "pret"
    assert docs["cours-scan.pdf"]["avertissement"]


def test_espace_prive(client):
    cours_id = creer_cours(client)
    deposer(client, cours_id)
    assert client.get("/tuteur/cours", headers=ETU2).json()["cours"] == []
    assert client.get(f"/tuteur/cours/{cours_id}", headers=ETU2).status_code == 404
    assert client.delete(f"/tuteur/cours/{cours_id}", headers=ETU2).status_code == 404
    r = deposer(client, cours_id, entetes=ETU2)
    assert r.status_code == 404


def test_question_sans_document_pret(client):
    cours_id = creer_cours(client)
    r = client.post(f"/tuteur/cours/{cours_id}/questions", json={"question": "Dérivée ?"}, headers=ETU1)
    assert r.status_code == 409
    assert r.json()["code"] == "aucun_document_pret"


def test_question_en_flux(client):
    cours_id = creer_cours(client)
    deposer(client, cours_id)
    attendre_pret(client, cours_id)
    r = client.post(f"/tuteur/cours/{cours_id}/questions",
                    json={"question": "Qu'est-ce qu'un nombre dérivé ?"}, headers=ETU1)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    ev = evenements(r.text)
    noms = [n for n, _ in ev]
    assert noms[0] == "debut" and noms[-1] == "fin"
    assert "texte" in noms and "sources" in noms
    debut = json.loads(ev[0][1])
    sources = json.loads(dict(ev)["sources"])["sources"]
    assert sources[0]["n"] == 1 and sources[0]["page"] == 12
    assert json.loads(ev[-1][1])["statut"] == "ok"

    # Question suivante dans la même conversation
    r2 = client.post(f"/tuteur/cours/{cours_id}/questions",
                     json={"question": "C'est hors cours ?", "conversation_id": debut["conversation_id"]},
                     headers=ETU1)
    ev2 = evenements(r2.text)
    assert json.loads(ev2[0][1])["conversation_id"] == debut["conversation_id"]
    assert json.loads(ev2[-1][1])["statut"] == "hors_cours"

    # Quota de 2 questions par heure atteint
    r3 = client.post(f"/tuteur/cours/{cours_id}/questions", json={"question": "Encore ?"}, headers=ETU1)
    assert r3.status_code == 429
    assert r3.json()["reessayer_apres"] > 0
    assert client.get("/tuteur/cours", headers=ETU1).json()["quota"]["questions_heure"] == 2

    # Avis sur la première réponse ; un autre étudiant ne peut pas en donner
    assert client.post(f"/tuteur/reponses/{debut['reponse_id']}/avis",
                       json={"utile": False, "commentaire": "Page fausse"}, headers=ETU1).status_code == 204
    assert client.post(f"/tuteur/reponses/{debut['reponse_id']}/avis",
                       json={"utile": True}, headers=ETU2).status_code == 404


def test_conversation_d_un_autre_etudiant(client):
    cours_id = creer_cours(client)
    deposer(client, cours_id)
    attendre_pret(client, cours_id)
    r = client.post(f"/tuteur/cours/{cours_id}/questions",
                    json={"question": "Q ?", "conversation_id": "v_inconnu"}, headers=ETU1)
    assert r.status_code == 404


def test_question_trop_longue(client):
    cours_id = creer_cours(client)
    deposer(client, cours_id)
    attendre_pret(client, cours_id)
    r = client.post(f"/tuteur/cours/{cours_id}/questions", json={"question": "x" * 1001}, headers=ETU1)
    assert r.json()["code"] == "question_trop_longue"


def test_suppressions(client, tmp_path):
    cours_id = creer_cours(client)
    doc_id = deposer(client, cours_id).json()["id"]
    fichiers = list((tmp_path / "depots" / "etu1").iterdir())
    assert len(fichiers) == 1
    assert client.delete(f"/tuteur/documents/{doc_id}", headers=ETU1).status_code == 204
    assert not list((tmp_path / "depots" / "etu1").iterdir())
    deposer(client, cours_id)
    assert client.delete(f"/tuteur/cours/{cours_id}", headers=ETU1).status_code == 204
    assert client.get(f"/tuteur/cours/{cours_id}", headers=ETU1).status_code == 404
    assert not list((tmp_path / "depots" / "etu1").iterdir())


def test_hors_demo_question_503(client, monkeypatch):
    cours_id = creer_cours(client)
    deposer(client, cours_id)
    attendre_pret(client, cours_id)
    from service.tuteur import config
    monkeypatch.setenv("TUTEUR_DEMO", "0")
    config.reglages.cache_clear()
    r = client.post(f"/tuteur/cours/{cours_id}/questions", json={"question": "Q ?"}, headers=ETU1)
    assert r.status_code == 503
    assert r.json()["code"] == "service_indisponible"
