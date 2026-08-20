# idac_drd

Dashboard do LIneA para acompanhar o progresso das **releases de dados**, do ingest (Rucio) até a publicação dos produtos científicos.

## Stack

- Django 5.2 + Django REST Framework (Postgres)
- React 18 + MUI v6 (Vite), montado em templates Django
- Login por sessão + CSRF; SAML opcional (LIneA/SATOSA)

## Funcionalidades

- Planos (draft) e releases (histórico oficial) em abas separadas
- Board de steps com status, responsável e bloqueios
- Gates de dependência: atividade não começa/termina antes dos pré-requisitos
- Export/import de planos em JSON
- Log de transições e analytics de gargalos
- Arquivo de releases (somente leitura); planos podem ser excluídos

## Setup local (Docker)

```bash
cp .env.example .env
docker compose up --build -d
```

- App: http://127.0.0.1/ (login `admin` / `admin`, criado no primeiro boot)
- Postgres: `localhost:5432` (`postgres` / `postgres` / `postgres`)

### Dados de exemplo

Importe as identidades de exemplo (assignees do board) uma única vez:

```bash
docker compose exec web python manage.py loaddata identities
```

Depois disso, novos registros são cadastrados via admin do Django.

### Frontend

O build do frontend é coordenado pelo Docker (sem `node` no host):

- **Dev**: o serviço `frontend` compila em watch — mudanças em `frontend/src/` re-buildam o bundle automaticamente e o Django o serve;
- **Produção**: a imagem `web` faz o build do frontend no próprio Dockerfile (multi-stage).

O bundle gerado (`idac_drd/static/frontend/`) é artefato de build — não vai para o git.

## Testes

```bash
docker compose exec -T web python -m pytest -q          # backend
docker compose run --rm frontend npx vitest run          # frontend
```

## Produção

Copie o conteúdo de `compose/production/` para o diretório de deploy (não aponte para o path no repositório):

```bash
# no servidor de produção
mkdir -p /caminho/deploy && cd /caminho/deploy
cp /caminho/repo/compose/production/docker-compose.yml .
cp /caminho/repo/compose/production/nginx.conf .
cp /caminho/repo/.env.example .env
# ajuste paths no docker-compose.yml: env_file → .env
# e o volume de certificados (se SAML) → ./certificates:/app/config/certificates:ro
```

No `.env`, defina no mínimo:

```env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<gerar abaixo>
DJANGO_ALLOWED_HOSTS=<hostname>
DATABASE_URL=postgres://USER:PASS@HOST:5432/DB
WEB_IMAGE_TAG=<hash-curto-do-commit>
```

```bash
# gerar secret
docker compose run --rm --no-deps web python -c "import secrets; print(secrets.token_urlsafe(50))"

# subir (imagem linea/idac_drd:<WEB_IMAGE_TAG> no Docker Hub)
docker compose pull
docker compose up -d --force-recreate
```

Django (uvicorn) atrás de nginx na porta 80; TLS encerrado no proxy do host. Certificados do SP (SAML) em `./certificates/` — ver [config/certificates/README.md](config/certificates/README.md).
