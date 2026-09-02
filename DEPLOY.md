# Déploiement (Render, gratuit)

Deux services séparés sur Render : l'**API** (service web Docker) et le **dashboard** (site statique). Free tier des deux côtés — aucune carte bancaire requise pour un site statique, et le service web gratuit suffit pour ce projet.

## Avant de commencer

- Un compte [Render](https://render.com) connecté à ton GitHub (`grimael`).
- Une clé API Groq ou Gemini à disposition (`GROQ_API_KEY` et/ou `GEMINI_API_KEY`) — nécessaire pour l'Assistant IA. Sans elle, tout le reste du dashboard fonctionne quand même ; seul `/agent/chat` répondra 503.
- Le dépôt [github.com/grimael/opendataviz-pipeline](https://github.com/grimael/opendataviz-pipeline) est déjà à jour et public.

## Étape 1 — Déployer l'API

Sur Render : **New +** → **Web Service** → connecte `grimael/opendataviz-pipeline`.

| Champ | Valeur |
|---|---|
| Environnement | Docker |
| Dockerfile Path | `api/Dockerfile` |
| Docker Build Context Directory | `.` (racine du dépôt) |
| Instance Type | Free |

Variables d'environnement (**Environment** → **Add Environment Variable**) :

| Clé | Valeur |
|---|---|
| `GROQ_API_KEY` | ta clé Groq (laisse vide si tu utilises seulement Gemini) |
| `GEMINI_API_KEY` | ta clé Gemini (laisse vide si tu utilises seulement Groq) |
| `LLM_PROVIDER` | `groq` (ou `gemini`) |
| `ALLOWED_ORIGINS` | laisse temporairement vide — à renseigner à l'étape 3, une fois l'URL du dashboard connue |

Clique **Deploy**. Le build prend plusieurs minutes : `docker build` installe les dépendances Python **et** exécute tout le pipeline ETL (extraction World Bank → imputation ML → projections) pour embarquer des données fraîches dans l'image — c'est normal, il n'y a pas de disque persistant sur le tier gratuit, donc les données ne peuvent être rafraîchies qu'en reconstruisant l'image (voir la note en bas de page).

Une fois déployé, Render donne une URL du type `https://opendataviz-api.onrender.com`. Vérifie avec :

```bash
curl https://opendataviz-api.onrender.com/health
```

Note cette URL — elle est nécessaire à l'étape 2.

## Étape 2 — Déployer le dashboard

**New +** → **Static Site** → même dépôt `grimael/opendataviz-pipeline`.

| Champ | Valeur |
|---|---|
| Root Directory | `dashboard` |
| Build Command | `npm install && npm run build` |
| Publish Directory | `dist` |

Variable d'environnement :

| Clé | Valeur |
|---|---|
| `PUBLIC_API_BASE_URL` | l'URL de l'API notée à l'étape 1, ex `https://opendataviz-api.onrender.com` |

Clique **Deploy**. Render donne une URL du type `https://opendataviz-dashboard.onrender.com`.

## Étape 3 — Boucler le CORS

Retourne sur le service **API** (étape 1) → **Environment** → renseigne enfin :

| Clé | Valeur |
|---|---|
| `ALLOWED_ORIGINS` | l'URL du dashboard notée à l'étape 2, ex `https://opendataviz-dashboard.onrender.com` |

Sauvegarder redémarre automatiquement le service. Sans cette étape, le navigateur bloquera les appels du dashboard vers `/agent/chat` et `/export/*` (CORS) — voir [SECURITY.md](SECURITY.md).

## Vérifier que tout fonctionne

Ouvre l'URL du dashboard et teste : la Vue d'ensemble (lit `public/data/*.json`, fonctionne toujours), l'onglet **Données** (télécharge via l'API), et l'**Assistant IA** (appelle l'API). Si l'Assistant ou le téléchargement échouent, vérifie dans l'ordre : `PUBLIC_API_BASE_URL` bien défini au *build* du dashboard (pas seulement au runtime — un site statique n'a pas de runtime), `ALLOWED_ORIGINS` sur l'API correspond exactement à l'origine du dashboard (schéma + domaine, sans slash final), et que le service API n'est pas encore en train de se réveiller (voir note ci-dessous).

## À savoir sur le tier gratuit Render

- **Mise en veille** : un service web gratuit inactif 15 minutes s'endort ; la requête suivante le réveille en ~30-60s (normal, pas un bug — le dashboard affichera une erreur réseau le temps que l'API redémarre, puis ça repasse).
- **Données figées entre deux déploiements** : comme il n'y a pas de disque persistant, les données ne se rafraîchissent qu'au *build* de l'image. Pour rafraîchir : **Manual Deploy** → **Deploy latest commit** sur le service API (même sans changement de code, ça relance le pipeline). Pour automatiser un rafraîchissement quotidien, le plus simple est d'ajouter l'URL de *Deploy Hook* de Render (Settings → Deploy Hook) comme étape finale du `.github/workflows/etl.yml` existant — non fait par défaut, à ajouter si besoin.
