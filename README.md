# WKFW Dashboard

LIneA **Data Release Workflow Dashboard** — track progress from Rucio ingest through scientific product publication across multiple data releases.

## Stack

- Django 4.2 + Django REST Framework + Postgres/SQLite
- Vite + React 18 + MUI v6 (islands mounted in Django templates)
- Bootstrap LIneA shell (appbar/footer), theme `#0989cb` / `#31297f`
- Optional `djangosaml2` (LIneA SATOSA), same pattern as [cutout](../cutout)

## Features

- Versioned **workflow templates** (seeded from DP2 drawio)
- **Data releases** cloned from templates (history preserved)
- Swimlane board with status, assignee, blocked reason
- **Hard dependency gates** (cannot start/finish until prerequisites are `done`)
- Add stages on active releases and on templates (staff)
- Transition log → duration / bottleneck analytics
- Archive releases (read-only)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env

cd frontend && npm install && npm run build && cd ..

python manage.py migrate
python manage.py seed_dp2_template
python manage.py create_release --name DP2 --from-template dp2
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1/ and sign in via `/admin/login/` (`admin` / `admin`).

Optional drawio label scan:

```bash
python manage.py seed_dp2_template --from-drawio "inputs/DP2 Data Workflow Diagram.drawio"
```

## SAML

Set `AUTH_SAML2_ENABLED=True`, `SITE_URL`, `SAML_IDP_METADATA_URL`, and place SP certs under `config/certificates/` (`private.key`, `public.cert`). Attribute maps live in `config/attribute-maps/`. Backend: `wkfw.users.saml2.LineaSaml2Backend`.

## API

- `/api/releases/`, `/api/releases/{slug}/activities/`
- `/api/activities/{id}/` (PATCH status/assignee)
- `/api/templates/`, `/api/templates/{key}/stages/`
- `/api/analytics/bottlenecks/?release=&compare=`
- Swagger: `/api/docs/` (admin)

Session auth + CSRF (`X-CSRFToken`), same-origin fetch.

## Tests

```bash
pytest wkfw/workflow/tests
```

## Docker

```bash
cp .env.example .env
docker compose up --build -d
```

- App: http://127.0.0.1/
- Postgres 18: `localhost:5432` (user/db/password: `postgres`)
