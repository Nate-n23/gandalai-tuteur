# Module tuteur de GANDAL-AI — lot A (socle et mode démo)

Ce dépôt contient le paquet `service/tuteur/`, à copier tel quel dans le dépôt de GANDAL-AI.
Il implémente le contrat d'API remis au frontend : 8 routes sous `/tuteur`, plus `GET /health`
qui existe déjà dans GANDAL-AI.

## Ce qui marche aujourd'hui

- Cours : créer, lister, lire, supprimer (avec fichiers, conversations et avis).
- Dépôt de fichiers : PDF, PowerPoint, Word ; taille maximale ; case « usage personnel » ;
  file d'attente avec position.
- Espace privé : un étudiant ne voit jamais les cours d'un autre (404, comme pour un cours inexistant).
- Quotas : cours par étudiant, fichiers par cours, questions par heure (avec `reessayer_apres`).
- Questions : contrôles, conversations, réponse en flux SSE (`debut`, `texte`, `sources`, `fin`, `erreur`).
- Avis sur une réponse.
- Erreurs au format `{"code", "message"}`, messages en français prêts à afficher.
- Mode démo (`TUTEUR_DEMO=1`) : la lecture des fichiers et les réponses sont simulées.

Ce qui reste : la vraie lecture des cours (lot B) et la vraie réponse (lot C). Hors mode démo,
les fichiers restent « en_attente » et les questions renvoient 503.

## Lancer le mode démo (pour le frontend)

```bash
pip install -r requirements.txt
TUTEUR_DEMO=1 TUTEUR_BASE=./tuteur.sqlite3 UPLOAD_DIR=./depots \
    uvicorn dev_app:app --host 0.0.0.0 --port 8090
```

- Contrat détaillé : http://<machine>:8090/docs
- Identité : en-tête `X-Utilisateur: <identifiant>` (provisoire, en attendant IAM).
- Un fichier passe « en_attente » 3 s, puis « en_lecture » 6 s, puis « pret ».
- Un nom de fichier contenant `illisible` finit en « erreur » ; contenant `scan`, « pret » avec un avertissement.
- Une question contenant « hors cours » reçoit une réponse `hors_cours`.

Exemple :

```bash
H="X-Utilisateur: etu1"; A=http://127.0.0.1:8090
curl -s -H "$H" -H "Content-Type: application/json" -d '{"titre": "Analyse 1"}' $A/tuteur/cours
curl -s -H "$H" -F "fichier=@cours.pdf" -F "usage_personnel=true" $A/tuteur/cours/<cours_id>/documents
curl -s -H "$H" $A/tuteur/cours/<cours_id>
curl -sN -H "$H" -H "Content-Type: application/json" -d '{"question": "Qu est-ce qu un nombre dérivé ?"}' \
    $A/tuteur/cours/<cours_id>/questions
```

## Brancher dans GANDAL-AI

1. Copier `service/tuteur/` dans le dépôt de GANDAL-AI.
2. Dans `service/app.py`, après la création de `app` :

   ```python
   from service.tuteur import installer
   installer(app)
   ```

3. Ajouter `python-multipart` aux dépendances.

`installer` crée la base SQLite si besoin, ajoute les routes et les gestionnaires d'erreurs.
Les erreurs de validation gardent le format FastAPI hors de `/tuteur`.

## Tests

```bash
python -m pytest -q
```

14 tests : chaque route, chaque erreur, l'espace privé, les quotas, le flux de réponse.

## Organisation

```text
service/tuteur/
├── __init__.py    installer(app)
├── config.py      réglages lus dans l'environnement (.env)
├── erreurs.py     format des erreurs du contrat
├── schemas.py     requêtes et réponses (Pydantic)
├── base.py        SQLite : cours, documents, file, conversations, réponses, avis
├── identite.py    qui est l'étudiant (provisoire)
├── quotas.py      limites par étudiant
├── routes.py      les routes du contrat
└── demo.py        lecture et réponses simulées
deploiement/env.exemple   tous les réglages
dev_app.py                application autonome, en attendant GANDAL-AI
```
