# IDAC BR Data Release Dashboard

LIneA **Data Release Workflow Dashboard** — track progress from Rucio ingest through scientific product publication across multiple data releases.

## Stack

- Django 4.2 + Django REST Framework + Postgres/SQLite
- Vite + React 18 + MUI v6 (islands mounted in Django templates)
- Bootstrap LIneA shell (appbar/footer), theme `#0989cb` / `#31297f`
- Optional `djangosaml2` (LIneA SATOSA)

## Features

- **Plans** (drafts) and **releases** (official history) separated in tabs
- Step board with status, assignee, blocked reason
- **Hard dependency gates** (cannot start/finish until prerequisites are `done`)
- Add steps/activities on plans and active releases
- Transition log → duration / bottleneck analytics
- Archive releases (read-only); delete draft plans (any authenticated user)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env

cd frontend && npm install && npm run build && cd ..

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1/ and sign in via `/admin/login/` (`admin` / `admin`).


## SAML

Set `AUTH_SAML2_ENABLED=True`, `SITE_URL`, `SAML_IDP_METADATA_URL`, and place SP certs under `config/certificates/` (`private.key`, `public.cert`). Attribute maps live in `config/attribute-maps/`. Backend: `idac_drd.users.saml2.LineaSaml2Backend`.

## API

- `/api/releases/`, `/api/releases/{slug}/steps/`, `/api/releases/{slug}/activities/`
- `/api/activities/{id}/` (PATCH status/assignee, POST `move` to reorder)
- `/api/analytics/bottlenecks/?release=&compare=`
- Swagger: `/api/docs/` (admin)

Session auth + CSRF (`X-CSRFToken`), same-origin fetch.

## Authorization & security

- **Modelo de autorização**: single-team interno — qualquer usuário autenticado (SAML ou login local) lê e opera **todas** as releases e atividades; não há conceito de equipe ou propriedade por release. Apenas `is_staff` pode criar usuários (`POST /api/users/`).
- **Destrutivos**: drafts (`status == planned`) podem ser apagados via API (DELETE → 204, com cascade); releases iniciadas ou arquivadas **não** (DELETE → 405). Atividades são deletáveis apenas em `todo` (em draft e em execução — nunca o histórico de uma atividade já iniciada); steps apenas vazios.
- **Rate limiting**: DRF `UserRateThrottle` em toda a API — `DJANGO_THROTTLE_RATE` (default `300/min` por usuário).
- **SAML**: debug (assertions em log, PII) apenas em dev — `SAML_DEBUG` (default = `DJANGO_DEBUG`).

## Tests

```bash
pytest idac_drd/workflow/tests
```

## Docker

```bash
cp .env.example .env
docker compose up --build -d
```

- App: http://127.0.0.1/
- Postgres 18: `localhost:5432` (user/db/password: `postgres`)
