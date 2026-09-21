# idac_drd

Dashboard do LIneA para acompanhar o progresso das **releases de dados**, do ingest (Rucio) até a publicação dos produtos científicos.

## Arquitetura

- Backend: Django 5.2, Django REST Framework e PostgreSQL, servido por Uvicorn.
- Frontend: React 18, MUI v6 e Vite, montado em templates Django.
- Autenticação: sessão Django e CSRF; SAML via LIneA/SATOSA é opcional.
- Produção: WhiteNoise serve os arquivos estáticos; o nginx do host encerra TLS e encaminha `/drd/` ao container.

O backend Django concentra os modelos, as regras de transição das releases, a API autenticada, o controle de permissões e as integrações externas. O frontend não acessa o banco nem os serviços externos diretamente: ele consome `/api/` usando a sessão e o token CSRF do Django.

Os apps principais são:

- `idac_drd/users/`: usuários de login e `ExternalIdentity`, que relaciona email a GitHub, Slack e GLPI;
- `idac_drd/workflow/`: releases, steps, atividades, sessões play/pause (effort), regras de negócio, páginas e API;
- `idac_drd/integrations/`: clientes e sincronização com GitHub, GLPI e Slack.

As integrações são executadas depois do commit da transação e em modo best-effort. Uma falha externa é registrada no log, mas não desfaz a operação realizada no dashboard.

Documentação de comportamento:

- [docs/work-sessions.md](docs/work-sessions.md) — play/pause, effort vs cycle, permissões;
- [docs/slack-hooks.md](docs/slack-hooks.md) — notificações Slack;
- [docs/glpi-hooks.md](docs/glpi-hooks.md) — sync de tickets GLPI.

## Funcionalidades

- Drafts, releases e arquivo em páginas separadas;
- board de steps com status, responsável e bloqueios;
- play/pause por atividade (uma sessão ativa por assignee) para medir effort/FTE — ver [docs/work-sessions.md](docs/work-sessions.md);
- gates de dependência entre atividades;
- exportação e importação de drafts em JSON;
- log de transições e relatório com cycle time e effort;
- arquivo de releases somente para leitura;
- criação opcional de issues GitHub, tickets GLPI e notificações Slack.

## Desenvolvimento local

### Pré-requisitos e inicialização

O ambiente local depende apenas de Docker com o plugin Compose. Node, Python e PostgreSQL não precisam estar instalados no host.

```bash
cp .env.example .env
docker compose up --build -d
```

O `docker-compose.yml` da raiz inclui `compose/local/docker-compose.yml` e inicia:

- `database`: PostgreSQL, publicado em `localhost:5432`;
- `web`: executa migrações, coleta arquivos estáticos, cria o superusuário local quando necessário e inicia o Uvicorn com reload;
- `frontend`: instala as dependências e mantém o Vite em modo watch;
- `nginx`: publica a aplicação em `http://127.0.0.1/` e encaminha as requisições para `web:8000`.

### Valores padrão locais

- Aplicação: `http://127.0.0.1/`
- Admin: `http://127.0.0.1/admin/`
- API: `http://127.0.0.1/api/`
- OpenAPI, somente para admin: `http://127.0.0.1/api/docs/`
- Superusuário: `admin`
- Senha: `admin`
- Email: `admin@linea.org.br`
- PostgreSQL: banco, usuário e senha `postgres`
- `DATABASE_URL`: `postgres://postgres:postgres@database:5432/postgres`
- `DJANGO_DEBUG`: `True`

Essas credenciais são exclusivas do ambiente local e não devem ser usadas em produção.

### Usuários e identidades externas

O superusuário `admin` é criado automaticamente apenas pelo compose local. A fixture `identities` não cria usuários de login: ela cadastra os responsáveis que podem ser associados às atividades e seus identificadores nos serviços externos.

Carregue a fixture uma vez em uma instalação nova:

```bash
docker compose exec web python manage.py loaddata identities
```

O arquivo está em `idac_drd/users/fixtures/identities.yaml`. Cadastros posteriores devem ser feitos no admin do Django, em `ExternalIdentity`.

### Frontend

No desenvolvimento, alterações em `frontend/src/` recompilam o bundle automaticamente. A saída em `idac_drd/static/frontend/` é um artefato de build e não é versionada.

Na imagem de produção, `compose/django/Dockerfile` usa build multi-stage: Node gera o bundle e a imagem Python recebe somente o resultado necessário. O Vite usa caminhos relativos, e o template informa ao React o `SCRIPT_NAME`; por isso as mesmas chamadas funcionam na raiz local e sob `/drd` em produção.

### Testes

```bash
docker compose exec -T web python -m pytest -q
docker compose run --rm frontend npx vitest run
docker compose exec web python manage.py check_integrations
```

O último comando faz um smoke test das integrações habilitadas.

## Deploy em produção

### Arquivos e imagem

`compose/production/docker-compose.yml` define somente o serviço `web`. Não há container nginx em produção: `compose/production/nginx.conf` é um fragmento de referência para o nginx já existente no host.

A imagem `linea/idac_drd` é publicada no Docker Hub pelo workflow `.github/workflows/docker-image.yml`. Use em `WEB_IMAGE_TAG` a tag correspondente ao commit que será implantado.

Copie os arquivos para um diretório de deploy independente do clone do repositório:

```bash
mkdir -p /caminho/deploy && cd /caminho/deploy
cp /caminho/repo/compose/production/docker-compose.yml .
cp /caminho/repo/compose/production/nginx.conf .
cp /caminho/repo/.env.example .env
```

Revise no compose o caminho de `env_file` e o volume dos certificados SAML. No `.env`, configure pelo menos:

```env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<segredo-aleatorio>
DJANGO_ALLOWED_HOSTS=www.linea.org.br,linea.org.br
DJANGO_FORCE_SCRIPT_NAME=/drd
DJANGO_CSRF_TRUSTED_ORIGINS=https://www.linea.org.br,https://linea.org.br
SITE_URL=https://www.linea.org.br/drd
DATABASE_URL=postgres://USER:PASS@HOST:5432/DB
WEB_IMAGE_TAG=<tag-da-imagem>
```

Gere uma chave secreta:

```bash
docker compose run --rm --no-deps web python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Suba ou atualize o serviço:

```bash
docker compose pull
docker compose up -d --force-recreate
```

Na inicialização, o container executa `migrate`, `collectstatic` e inicia `config.asgi:application` com Uvicorn na porta 8000. O compose publica essa porta como `8193` no host. Diferentemente do ambiente local, produção não cria um superusuário automaticamente.

### O caso especial `/drd`

A aplicação compartilha o domínio do LIneA e é publicada em `https://www.linea.org.br/drd/`, não na raiz. O nginx externo remove `/drd` antes de encaminhar a requisição ao Uvicorn, enquanto o Django precisa continuar gerando URLs públicas com esse prefixo.

O vhost completo do domínio não faz parte deste repositório. O operador deve incorporar ao nginx do LIneA a configuração equivalente ao fragmento versionado em `compose/production/nginx.conf`:

```nginx
location = /drd {
    return 301 /drd/;
}

location /drd/ {
    rewrite ^/drd/(.*) /$1 break;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_pass http://127.0.0.1:8193;
    proxy_redirect off;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    client_max_body_size 50M;
}
```

O upstream pode ser outro host acessível pelo proxy, conforme a topologia da infraestrutura. O ponto obrigatório é remover o prefixo antes do Uvicorn, preservar `Host` e `X-Forwarded-Proto` e desabilitar a reescrita automática de redirects pelo nginx. O TLS termina no proxy do host.

### Adaptações do Django para aplicações em subpath

Aplicações Django publicadas sob um prefixo precisam tratar separadamente dois caminhos:

- caminho público, visto pelo navegador: `/drd/...`;
- `PATH_INFO` recebido pelo Uvicorn depois do rewrite do nginx: `/...`.

Configurar apenas o rewrite no nginx não basta. Sem as adaptações abaixo, links reversos, redirects, cookies, login do admin, arquivos estáticos e chamadas do frontend podem escapar para a raiz do domínio.

#### Settings de produção

`config/settings/production.py` lê `DJANGO_FORCE_SCRIPT_NAME`, remove uma eventual barra final e, quando o valor não está vazio, aplica:

```python
FORCE_SCRIPT_NAME = _script_name
STATIC_URL = f"{_script_name}/static/"
MEDIA_URL = f"{_script_name}/media/"
CSRF_COOKIE_PATH = _script_name
SESSION_COOKIE_PATH = _script_name
WHITENOISE_STATIC_PREFIX = "/static/"
```

Cada item resolve uma parte diferente:

- `FORCE_SCRIPT_NAME` informa ao Django que a aplicação ocupa `/drd` e faz `reverse()`, `{% url %}` e `request.META.SCRIPT_NAME` gerarem caminhos públicos prefixados;
- `STATIC_URL` e `MEDIA_URL` geram links públicos como `/drd/static/...` e `/drd/media/...`;
- `CSRF_COOKIE_PATH` e `SESSION_COOKIE_PATH` restringem os cookies à aplicação; `CSRF_COOKIE_NAME` (`idac_drd_csrftoken`) e `SESSION_COOKIE_NAME` (`idac_drd_sessionid`) evitam colisão de nome com outros sistemas no mesmo domínio;
- `WHITENOISE_STATIC_PREFIX` permanece `/static/` porque o nginx já removeu `/drd` quando a requisição chega ao WhiteNoise.

O mesmo arquivo também configura:

- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, para o Django reconhecer a conexão original como HTTPS;
- cookies de sessão e CSRF seguros;
- `CSRF_TRUSTED_ORIGINS` a partir de `DJANGO_CSRF_TRUSTED_ORIGINS`;
- redirecionamento para HTTPS e políticas HSTS;
- `CompressedManifestStaticFilesStorage` para arquivos estáticos versionados.

O nginx precisa enviar `X-Forwarded-Proto` corretamente. Caso contrário, o Django pode interpretar a requisição como HTTP e produzir redirects incorretos ou repetidos.

#### URLs de login e parâmetros `next`

Ainda em `config/settings/production.py`, `_with_script_name()` adapta `LOGIN_URL`, `LINEA_LOGIN_URL` e `RUBIN_LOGIN_URL`.

A função:

- prefixa somente URLs locais iniciadas por `/`;
- não duplica `/drd` quando o prefixo já existe;
- preserva query string e fragmento;
- também prefixa caminhos locais presentes no parâmetro `next`.

Assim, por exemplo, `/admin/login/?next=/` se torna `/drd/admin/login/?next=/drd/`. URLs externas do provedor de identidade não são alteradas.

#### `PrefixRedirectMiddleware`

`config.middleware.PrefixRedirectMiddleware` foi criado porque nem todo header `Location` produzido durante login, logout ou validações respeita `FORCE_SCRIPT_NAME`. Como o nginx entrega ao Django um caminho sem `/drd`, alguns redirects ainda podem sair como `/admin/login/` ou `/`.

Quando `DJANGO_FORCE_SCRIPT_NAME` está configurado, o middleware é inserido no início da lista:

```python
MIDDLEWARE = ["config.middleware.PrefixRedirectMiddleware", *MIDDLEWARE]
```

Por estar na camada externa, ele recebe a resposta final depois dos demais middlewares. Se houver um header `Location`, `prefix_location()`:

1. adiciona `/drd` a caminhos absolutos locais iniciados por `/`;
2. não duplica o prefixo quando ele já está presente;
3. preserva query string e fragmento;
4. mantém redirects relativos sem alteração;
5. em URLs completas, só modifica hosts presentes em `ALLOWED_HOSTS`;
6. não modifica redirects para hosts externos, como o IdP SAML.

Esse último controle evita transformar, por exemplo, uma URL do SATOSA em uma URL sob `/drd`. Os casos de raiz, admin, prefixo duplicado, query string, host permitido e IdP externo estão cobertos em `config/test_middleware.py`.

#### Login do admin

`config/urls.py` contém um ajuste específico para o formulário de login do admin. O Django monta `app_path` usando `request.get_full_path()`, que nesse cenário contém `/admin/login/`, sem o `SCRIPT_NAME`. Sem a correção, o formulário faz POST na raiz do domínio e pode cair em outra aplicação.

O wrapper `_admin_login_prefixed()` recalcula o campo com:

```python
get_script_prefix().rstrip("/") + request.get_full_path()
```

Em seguida, ele substitui `admin.site.login` pelo wrapper. Com isso, o POST é enviado para `/drd/admin/login/`.

#### Frontend e API

O frontend também não pode manter `/api/...` como caminho absoluto fixo. Em `idac_drd/templates/pages/_react_mount.html`, o Django publica:

```html
data-api-prefix="{{ request.META.SCRIPT_NAME }}"
```

`frontend/src/api.js` expõe `appUrl()`, que lê esse valor e acrescenta o prefixo a todo caminho iniciado por `/`, sem duplicá-lo. As chamadas da API e os links/redirects de página no React (por exemplo `/releases/<slug>/`) passam por essa função. Assim:

- localmente, `SCRIPT_NAME` é vazio e o caminho continua `/api/...` ou `/releases/...`;
- em produção, `SCRIPT_NAME` é `/drd` e o caminho passa a `/drd/api/...` ou `/drd/releases/...`.

O template também usa o prefixo para construir o parâmetro `next` do login. O Vite usa `base: "./"`, permitindo que os assets do bundle sejam carregados sob `/static/...` ou `/drd/static/...`.

#### Checklist para outras aplicações Django sob um prefixo

Para publicar outra aplicação com a mesma topologia:

1. faça o proxy remover o prefixo antes de encaminhar ao servidor ASGI/WSGI;
2. configure `FORCE_SCRIPT_NAME` com o caminho público;
3. prefixe `STATIC_URL`, `MEDIA_URL`, URLs de login e parâmetros `next`;
4. alinhe o prefixo interno do WhiteNoise ao caminho recebido após o rewrite;
5. restrinja os paths dos cookies de sessão e CSRF;
6. encaminhe `Host` e `X-Forwarded-Proto` e configure `SECURE_PROXY_SSL_HEADER`;
7. revise todos os headers `Location`, sem alterar redirects para serviços externos;
8. verifique formulários que usam `request.get_full_path()`, especialmente o admin;
9. forneça o `SCRIPT_NAME` ao frontend para chamadas de API e links de página;
10. teste raiz, admin, login/logout, SAML, API, arquivos estáticos, query strings e redirects externos.

As URLs públicas esperadas são:

- `https://www.linea.org.br/drd/`
- `https://www.linea.org.br/drd/admin/`
- `https://www.linea.org.br/drd/api/`
- `https://www.linea.org.br/drd/static/`

### Usuários, SAML e certificados

Em produção, crie um superusuário manualmente quando o login administrativo local for necessário:

```bash
docker compose exec web python manage.py createsuperuser
```

Em uma instalação nova, carregue também as identidades externas usadas para relacionar os responsáveis do workflow aos usuários do GitHub, Slack e GLPI:

```bash
docker compose exec web python manage.py loaddata identities
```

Execute esse comando somente na carga inicial. Em um banco já populado, a fixture pode entrar em conflito com chaves primárias existentes; nesse caso, cadastre ou atualize os registros de `ExternalIdentity` pelo admin.

Com SAML habilitado, usuários desconhecidos são criados no primeiro login e seus grupos são sincronizados pelo atributo `member`. Grupos listados em `INTERNAL_GROUPS` não são removidos durante essa sincronização.

Configure `AUTH_SAML2_ENABLED`, `SITE_URL`, `LINEA_LOGIN_URL`, `RUBIN_LOGIN_URL` e `SAML_SP_NAME`. Monte os certificados em `/app/config/certificates` como `private.key` e `public.cert`. Consulte `config/certificates/README.md` e registre os metadados do SP junto ao serviço de identidade do LIneA.

`User` representa uma conta que entra na aplicação. `ExternalIdentity` representa um responsável do workflow e seus IDs externos. Eles são cadastros distintos. O play/pause casa o login com o assignee pelo **email** (`User.email` = `ExternalIdentity.email`); superusuário também pode controlar o timer. Detalhes em [docs/work-sessions.md](docs/work-sessions.md).

## Integrações

As integrações são opcionais e ficam desabilitadas por padrão. A configuração de ambiente está em `.env.example`, os settings em `config/settings/base.py` e os clientes em `idac_drd/integrations/`.

### GitHub

```env
GH_ENABLED=True
GH_TOKEN=<token>
```

O token deve pertencer a uma conta ou bot autorizado a criar e editar issues nos repositórios necessários da organização `linea-it` e a consultar e alterar itens do GitHub Project V2 **Software**, número 39. Conceda somente acesso aos repositórios usados pelo workflow. Para Project V2, o token precisa ao menos de leitura de projeto (`read:project`) e das permissões de escrita exigidas pelas mutations GraphQL e pela criação/edição de issues.

A integração recusa sincronização de issues para repositórios fora da organização `linea-it`. Dessa forma, toda a automação permanece vinculada aos repositórios do LIneA e ao projeto Software.

Fallbacks:

- integração desabilitada: nenhuma escrita é feita;
- falha na API: a operação principal continua e o erro é registrado;
- responsável sem `github_handle`: a issue é criada sem assignee;
- sem acesso ao Project V2: a issue pode ser criada, mas sua inclusão ou atualização no projeto é ignorada.

Implementação:

- `idac_drd/integrations/github.py`: cliente GitHub e Project V2;
- `idac_drd/integrations/sync.py`: regras e restrições de sincronização;
- `idac_drd/workflow/api/views.py`: opções usadas pelo frontend.

### GLPI

```env
GLPI_ENABLED=True
# 186.232.60.56: https://helpdesk-dev.linea.org.br
# 186.232.60.44: https://helpdesk.linea.org.br
GLPI_API_URL=http://186.232.60.56/apirest.php
GLPI_USER=<usuario-de-servico>
GLPI_PASSWORD=<senha>
GLPI_APP_TOKEN=<app-token>
```

helpdesk-dev usa HTTP (sem `https`). O cliente da API aceita **somente** origem `10.24.2.65` a `10.24.2.94` (`ERROR_NOT_ALLOWED_IP` fora desse range). O host do DRD em produção precisa estar nesse intervalo.

#### 1. Habilitar e registrar o cliente da API

No GLPI, acesse **Setup → General → API** e configure:

- **Enable Rest API:** `Yes`;
- **Enable login with credentials:** `Yes`, pois o cliente abre a sessão com `GLPI_USER` e `GLPI_PASSWORD`;
- **Enable login with external token:** `Yes`;
- adicione e habilite um cliente de API para a aplicação, por exemplo `IDAC-DRD`;
- copie o App Token desse cliente para `GLPI_APP_TOKEN`;
- **IPv4 address range:** `10.24.2.65-10.24.2.94`.

O campo **URL of the API** no GLPI pode mostrar o hostname; no DRD o helpdesk-dev aponta para `http://186.232.60.56/apirest.php`. O cliente chama `initSession` com login e senha e envia o header `App-Token` em todas as requisições.

#### 2. Configurar o perfil do usuário de serviço

Associe o usuário usado em `GLPI_USER` ao perfil **Webservices**. Em **Administration → Profiles → Webservices → Administration**, habilite:

- **Users → Read**.

Essa permissão de leitura de usuários é a configuração mostrada no perfil e permite trabalhar com os IDs usados na atribuição. O perfil também precisa autorizar as operações de tickets utilizadas pela integração:

- criar, ler e atualizar tickets;
- ler os usuários associados ao ticket;
- atribuir e remover responsáveis;
- criar acompanhamentos (`Followup`);
- adicionar acompanhamento a tickets fechados.

A última permissão é necessária porque o fluxo registra a nota antes de fechar o ticket. A atribuição usa o campo virtual escalar `_users_id_assign`; o direito **Users → Read**, isoladamente, não substitui as permissões de tickets e acompanhamentos.

O identificador GLPI de cada responsável fica em `ExternalIdentity.glpi_id`. Sem ele, o ticket é mantido sem atribuição. Tickets fechados, status 6, são terminais e não são reabertos automaticamente.

Fallbacks:

- integração desabilitada: nenhum ticket é criado ou alterado;
- falha de autenticação ou API: a operação principal continua e o erro é registrado;
- responsável sem `glpi_id`: a atribuição é ignorada;
- atividade bloqueada: o ticket só é criado depois do desbloqueio.

Implementação e documentação:

- `idac_drd/integrations/glpi.py`;
- `idac_drd/integrations/sync.py`;
- `docs/glpi-hooks.md`.

### Slack

Crie um Slack App para o workspace do LIneA, instale-o no workspace e convide o bot para o canal de destino.

Escopos OAuth necessários:

- `chat:write`;
- `users:read`;
- `users:read.email`;
- `im:write`;
- `channels:read`.

Configure:

```env
SLACK_ENABLED=True
SLACK_BOT_TOKEN=<xoxb-token>
SLACK_CHANNEL_ID=<id-do-canal>
SLACK_DEV_USER_ID=<id-do-usuario-de-fallback>
SITE_URL=https://www.linea.org.br/drd
```

A integração apenas envia mensagens; ela não recebe eventos nem interações. `SITE_URL` é usado nos links das notificações. O `slack_id` de cada responsável fica em `ExternalIdentity`.

Fallbacks:

- sem canal configurado, `post_slack_message` tenta enviar uma mensagem direta para `SLACK_DEV_USER_ID`;
- sem `slack_id`, a menção ou mensagem direta ao responsável é ignorada, mas a mensagem do canal ainda pode ser enviada;
- falha da API: a operação principal continua e o erro é registrado;
- eventos de atividades só notificam quando a release está ativa.

As threads são associadas aos steps por `ReleaseStep.slack_thread_ts`.

Implementação e documentação:

- `idac_drd/integrations/slack.py`;
- `idac_drd/integrations/notify.py`;
- hooks em `idac_drd/workflow/services.py`;
- `docs/slack-hooks.md`.

### Validação

Depois de preencher o `.env`, valide as integrações dentro do container:

```bash
docker compose exec web python manage.py check_integrations
```

Para cadastrar ou corrigir `github_handle`, `slack_id` e `glpi_id`, use `ExternalIdentity` no admin do Django.
