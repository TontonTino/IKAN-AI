# ikanai-agent

Service FastAPI **indépendant** portant l'agent IA conversationnel IKAN AI
(Q&A managers, brouillons d'action, alertes automatiques sur feedback
critique). Déployé séparément du backend principal (`apps/api`), sur son
propre port (8001), avec son propre `requirements.txt` et son propre
`.env` — mais connecté à la **même base PostgreSQL**.

Construit à partir du prototype `Agent IA/` (livré par Lionel, Chief AI
Officer) en remplaçant `mock_store` (données en mémoire) par de vraies
requêtes SQLAlchemy sur les tables du backend principal.

## Architecture

```
Backend principal (apps/api, port 8000)          ikanai-agent (port 8001)
──────────────────────────────────────           ──────────────────────────
analyse_service.py                                POST /webhook/analyse-complete
  → crée AnalyseIA                                  (secret partagé, PAS de JWT)
  → POST webhook  ───────────────────────────────►    → declencher_alerte_si_critique()
                                                        → génère un brouillon (table
                                                          actions_agent, propre à ce service)

Dashboard ──── Bearer JWT (même SECRET_KEY) ────►  POST /agent/ask
                                                    POST /agent/actions/brouillon
                                                    GET  /agent/actions
                                                    POST /agent/actions/{id}/valider
                                                    POST /agent/actions/{id}/rejeter
                                                          │
                                                          ▼
                                            même base PostgreSQL que apps/api
                                            LECTURE : feedbacks, analyses_ia, qr_codes,
                                                      agences, organisations, utilisateurs,
                                                      demandes_contact
                                            ÉCRITURE : actions_agent (uniquement)
```

- **Base de données partagée, schéma séparé de responsabilité** : ce
  service lit les tables du backend principal via des modèles SQLAlchemy
  en lecture seule (`app/models/readonly.py`, mappés sur un `Base` dédié,
  jamais géré par Alembic) et n'écrit que dans `actions_agent`, sa propre
  table, gérée par sa propre migration (`alembic/versions/001_action_agent.py`).
- **Auth** : ce service n'émet jamais de JWT (pas de `/login`). Il
  **vérifie** les tokens émis par le backend principal, avec la même
  `SECRET_KEY`/`ALGORITHM` — voir `app/api/deps.py`, calqué sur
  `apps/api/app/api/deps.py`.
- **Webhook** : le backend principal doit appeler
  `POST /webhook/analyse-complete` juste après avoir créé une `AnalyseIA`.
  Protégé par un header `X-Webhook-Secret` comparé à `WEBHOOK_SECRET`
  (comparaison à temps constant), pas par JWT — c'est un appel
  service-à-service.

## Installation

```bash
cd ikanai-agent
pip install -r requirements.txt
cp .env.example .env
# Renseigner DATABASE_URL (identique à apps/api/.env), SECRET_KEY (identique
# à apps/api/.env), WEBHOOK_SECRET, MISTRAL_API_KEY, WHATSAPP_*
alembic upgrade head   # crée uniquement la table actions_agent
uvicorn app.main:app --reload --port 8001
```

## Endpoints

| Méthode | Route | Auth | Description |
|---|---|---|---|
| POST | `/agent/ask` | Bearer JWT (CX/Agency Manager/Admin) | Q&A conversationnel |
| POST | `/agent/actions/brouillon` | Bearer JWT | Génère un brouillon manuellement |
| GET | `/agent/actions` | Bearer JWT | Liste des brouillons `EN_ATTENTE` |
| POST | `/agent/actions/{id}/valider` | Bearer JWT | Valide + tente l'envoi WhatsApp en tâche de fond |
| POST | `/agent/actions/{id}/rejeter` | Bearer JWT | Rejette un brouillon |
| POST | `/webhook/analyse-complete` | `X-Webhook-Secret` | Appelé par le backend principal |

Contrat `POST /agent/ask` :
```json
// Requête
{"question": "Y a-t-il des alertes critiques ?", "agence_id": "uuid-ou-absent", "jours": 7}
// Réponse
{"intention": "alertes_critiques", "reponse": "texte Mistral", "donnees": [...]}
```
`agence_id` doit être un UUID valide ou **absent** du JSON — jamais `""`.

## Décisions prises en s'écartant du prototype (et pourquoi)

1. **`necessite_verification` n'existe pas dans `AnalyseIA` côté backend
   principal** (vérifié : absent du modèle SQLAlchemy et de la migration
   Alembic initiale — voir audit préalable). Ce champ est donc **dérivé**
   de `discordance_detectee` (note client incohérente avec le sentiment
   détecté), le signal réel le plus proche conceptuellement. Voir la note
   en tête de `app/agent/queries.py`. Si le backend principal ajoute un
   jour une vraie colonne `necessite_verification`, il suffit de modifier
   `_ligne_vers_dict()` dans ce fichier.

2. **`intent_classifier.py` est un moteur à mots-clés déterministe**, pas
   le zero-shot Hugging Face du prototype (`nlp_provider.py`). Le
   `GUIDE_INTEGRATION.md` du prototype indique explicitement que
   `nlp_provider.py` est *"NON UTILISÉ en prod, conservé comme
   référence"* — cette version suit donc la même logique que le reste du
   pipeline IKAN AI (`sentiment.py` / `classification_service.py` côté
   backend principal sont eux aussi 100% lexicaux, sans dépendance
   réseau). `HF_API_KEY` reste dans la configuration si cette approche
   devait être remplacée par le modèle zero-shot plus tard.

3. **L'envoi WhatsApp est découplé de la validation.**
   `action_service.valider_action()` ne fait plus qu'un `UPDATE` DB
   synchrone. `action_service.envoyer_whatsapp_si_applicable()` est une
   fonction séparée, destinée à `BackgroundTasks`, qui ouvre **sa propre
   session DB** (`SessionLocal()`) — la session de la requête HTTP
   d'origine est fermée avant qu'une tâche de fond ne s'exécute.

4. **`declencher_alerte_si_critique()` est idempotent** : si un brouillon
   `REPONSE_CLIENT` existe déjà pour un `feedback_id` donné, il est
   retourné tel quel plutôt que dupliqué. Nécessaire car un webhook HTTP
   peut être appelé plusieurs fois (retry réseau côté backend principal).

5. **`SECRET_KEY`/`DATABASE_URL`/`WEBHOOK_SECRET` n'ont pas de valeur par
   défaut** dans `app/config/settings.py` — le service refuse de démarrer
   sans `.env` correctement rempli, plutôt que de retomber sur une valeur
   hardcodée (contrairement à `apps/api/app/core/config.py` qui a un
   `DATABASE_URL` par défaut pointant vers une vraie instance Render — à
   corriger côté backend principal, hors périmètre de ce projet).

## Ce qu'il reste à faire côté backend principal (NON modifié ici)

Ce dossier est volontairement isolé de `apps/api`. Deux ajouts sont
nécessaires côté backend principal pour que le webhook fonctionne (à
faire manuellement, ce projet ne les modifie pas) :

1. Ajouter `WEBHOOK_SECRET` (même valeur que dans `ikanai-agent/.env`) et
   `AGENT_WEBHOOK_URL` (ex. `http://localhost:8001/webhook/analyse-complete`
   en dev) dans `apps/api/app/core/config.py` et `apps/api/.env`.
2. Dans `apps/api/app/services/ai/analyse_service.py`, juste après
   `db.commit()` (persistance de l'`AnalyseIA` et des recommandations),
   appeler le webhook en tâche de fond (HTTP POST, ne doit jamais faire
   échouer l'analyse si l'agent est indisponible) :
   ```python
   requests.post(
       settings.AGENT_WEBHOOK_URL,
       json={"feedback_id": str(feedback_id), "criticite": criticite_enum.value},
       headers={"X-Webhook-Secret": settings.WEBHOOK_SECRET},
       timeout=5,
   )
   ```

## Limites connues / suite possible

- Aucun test automatisé n'a encore été porté depuis `tests/test_agent.py`
  du prototype (ils mockaient `mock_store` et les providers ; à réécrire
  avec une base de test ou des fixtures SQLAlchemy).
- Le classifieur d'intention par mots-clés est une base fonctionnelle,
  pas calibrée sur des données réelles — à affiner une fois des questions
  réelles de managers observées.
