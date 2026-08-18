# Hooks GLPI no fluxo da Activity

Comportamento atual da integração GLPI no fluxo de atividades.

---

## 1. Visão geral

Toda escrita no fluxo da Activity agenda `_sync_later(activity, actor)` via
`transaction.on_commit` + `_safe` ([services.py](idac_drd/workflow/services.py)):
a chamada HTTP roda **depois** do commit e um erro pós-commit vira log, nunca
quebra o fluxo. A decisão de aplicar fica dentro de
`sync_activity()` ([sync.py](idac_drd/integrations/sync.py)):

- gate da release: `release.status in (ACTIVE, COMPLETED)` — o `COMPLETED`
  entra no gate porque a aprovação da última atividade marca a release
  completed **antes** da sync agendada rodar; sem isso o ticket final nunca
  fecharia;
- gate da flag: `GLPI_ENABLED` (default `False`).

Cada atividade de uma release em execução espelha-se num ticket GLPI:
criado quando a atividade fica **disponível** (todo), o executor é atribuído
na execução, o status acompanha a atividade e cada mudança registra uma nota
na timeline. Best-effort por design: falha de API loga warning e não altera o
estado do app.

## 2. Cliente GLPI ([glpi.py](idac_drd/integrations/glpi.py))

Uma sessão nova por chamada (`initSession` login/password → Session-Token;
App-Token em todos os requests) — stateless, sem cache (tokens expiram em
~30min). Credenciais obrigatórias: `GLPI_API_URL` (https), `GLPI_USER`,
`GLPI_PASSWORD`, `GLPI_APP_TOKEN`; ausentes → `ImproperlyConfigured` só na
chamada.

| Método | Chamada | Uso |
|---|---|---|
| `create_ticket` | `POST /Ticket` com `{"input": {...}}` | criar; atores via campo virtual `_users_id_*` (sem underscore é **ignorado silenciosamente**) |
| `update_ticket` | `PUT /Ticket/{id}` com `{"input": {...}}` | status, título, body, pending_reason |
| `get_ticket` | `GET /Ticket/{id}` | status atual (idempotência + guarda de terminal) |
| `get_ticket_users` | `GET /Ticket/{id}/Ticket_User/` | atores atuais (`users_id` + `type` 1=requester, 2=assign, 3=observer) |
| `assign_ticket` | `PUT` com `{"_users_id_assign": int}` | atribuir executor — **escalar**; `_itil_assign` em LISTA é ignorado silenciosamente |
| `unassign_ticket` | `DELETE /Ticket/{id}/Ticket_User/{ticket_user_id}` | remover ator (desatribuição no dashboard) |
| `add_followup` | `POST /Ticket/{id}/ITILFollowup` | nota na timeline (`items_id`+`itemtype`+`content`) |
| `check` | `getMyEntities` | smoke test do `check_integrations` |

Pegadinhas validadas ao vivo (helpdesk-dev 10.0.20):

- **`GET /Ticket/{id}` sempre devolve os atores como `None`** — eles vivem em
  `Ticket_User`; a única verificação é via `get_ticket_users`.
- **Atribuir o primeiro executor promove o ticket para `processing (assigned)`**
  sozinho — promoção automática é feature, não bug (não enviamos status junto).
- **Followup:** o app tem o right no perfil Webservices (201 OK no ticket 143).
  Followup em ticket **fechado** exige o right "Add followup to closed tickets"
  — por isso a sync fecha o ticket **depois** da nota, nunca antes.
- O right de Users Read foi liberado no perfil, mas não era o bloqueio dos
  atores — era o nome do campo (`_users_id_*`).

## 3. Quando a sync roda (disparos em [services.py](idac_drd/workflow/services.py))

| Operação | Efeito |
|---|---|
| `transition_activity` | toda transição de status agenda `_sync_later(activity, actor)` |
| `add_activity` | agenda (a release precisa estar ACTIVE para criar ticket; o gate está na sync, o hook é incondicional) |
| `start_release` | agenda uma sync por atividade |
| `_clone_structure` | release clonada já em execução cria issue/ticket por atividade |
| `move_activity` | re-sincroniza (o **título** do ticket contém o label do step) |
| `update_release_step` | re-sincroniza as atividades do step (título do ticket) |
| `delete_activity` | agenda `cleanup_deleted_activity` (fecha issue/ticket órfãos) |
| edição de campos | `ActivityViewSet.partial_update` agenda com `actor=request.user` (nota de edição) |

## 4. Ciclo de vida do ticket ([sync.py](idac_drd/integrations/sync.py))

### 4.1 Criação — quando a atividade fica disponível

```python
if not activity.glpi_ticket_id:
    if activity.status == Activity.Status.BLOCKED:   # bloqueada nunca gera ticket
        return
    body = _ticket_body(activity)
    ticket = client.create_ticket(name=_ticket_name(activity), content=body)
    Activity.objects.filter(pk=activity.pk).update(glpi_ticket_id=ticket["id"], glpi_ticket_content=body)
```

- Ticket nasce **sem atores**, em `new` (1). A passada continua: atribui o
  executor e ajusta o status do ticket novo na mesma sync.
- **`todo` gera ticket** (a atividade está disponível); `blocked` (pré-requisitos
  pendentes) nunca — não polui o helpdesk com o que não pode começar.
- Título: `{release.name} - {step.label}: {activity.label}` (contexto no
  helpdesk). Corpo: HTML mínimo com as seções descrição/objetivos/notas
  (fallback `<p>Sem descrição.</p>` quando vazio — a API rejeita content em
  branco). `glpi_ticket_content` guarda o snapshot do que escrevemos.
- Criar ticket não gera nota: o próprio `content` descreve a atividade.

### 4.2 Mapeamento de status

| Status do dashboard | Ação GLPI | Estado GLPI |
|---|---|---|
| `todo` | — (criação já aconteceu) | `new` (1) |
| `in_progress` | atribuir executor (`_users_id_assign`); status 2 se difere | `processing` (2) |
| `blocked` | `status=4` + `pending_reason` = `blocked_reason` | `pending` (4) |
| `in_review` | `status=4` + `pending_reason` = `Aguardando revisão da atividade "X"` | `pending` (4) |
| rejeição (`in_review`→`in_progress`) | `status=2` | `processing` (2) |
| aprovação (`in_review`→`done`) | nota na timeline, depois `status=6` | `closed` (6, grava solvedate) |

`GLPI_STATUS` em [sync.py](idac_drd/integrations/sync.py): `TODO:1,
IN_PROGRESS:2, BLOCKED:4, IN_REVIEW:4, DONE:6`. Aprovação (`done`) fecha com
`status=6` direto; o código **não** registra ITILSolution (ver §8).

### 4.3 Atribuição — só em execução, idempotente

Só roda quando `activity.status == IN_PROGRESS`:

- `assignee is None` → remove **todos** os executores atuais do ticket
  (desatribuir no dashboard espelha no ticket);
- `assignee.glpi_id is None` → loga warning e pula (sem chamada de API para
  resolver — o id é preenchido via admin/fixture);
- senão, atribui só se o `glpi_id` ainda não está em `Ticket_User`
  (re-atribuir o mesmo ator dispara `_forcenotif`/notificações em vão) e
  remove quem deixou de ser executor (troca de assignee).

### 4.4 Conteúdo — título, body e motivo acompanham a activity

`_ticket_changes()` compara o estado atual com o ticket e lista o que difere
(`título`, `descrição`, `objetivos`, `notas`, `motivo`, `status`); um único
`PUT` aplica tudo. Comparações:

- **título** contra `ticket.name` (renomear release/step/atividade re-sincroniza);
- **conteúdo** contra `glpi_ticket_content` (o snapshot local) e **não** contra
  o GET — o GLPI devolve HTML normalizado e a comparação contra o GET acharia
  mudança em toda sync. `NULL` (legado) compara contra o GET. Seções removidas
  são detectadas pelos headers `Objetivos:`/`Notas:`;
- **pending_reason** só quando a API devolve o campo (se nunca vier, não há
  como comparar — e não queremos PUT em toda sync). Em `blocked`/`in_review`,
  o motivo é re-enviado junto de qualquer PUT que aconteça.

### 4.5 Notas na timeline (o que aconteceu)

Cada sync que escreve algo (ou atribui executor) registra um followup. **Sem
prefixo `[Dashboard]`** — o título do ticket (`RELEASE - STEP`) já indica que a
nota vem do dashboard. O autor entra na nota: `(requisitado por {ator})` nas
transições (o ator vem da `ActivityTransition` mais recente), `(modificado por
{ator})` nas edições.

| Evento | Texto da nota |
|---|---|
| início da execução | `Atividade "«label»" iniciada — executor: «nome».` |
| bloqueio | `Atividade "«label»" bloqueada: «blocked_reason».` |
| envio à revisão | `Atividade "«label»" enviada para revisão — aguardando aprovação.` |
| rejeição | `<p><strong>Revisão recusada</strong></p><p>«comment». Voltou para execução. (requisitado por «ator»)</p>` (HTML mínimo; o GLPI renderiza na timeline) |
| aprovação | `Atividade "«label»" aprovada e concluída.` |
| edição de campos | `Atividade "«label»" — executor alterado para «nome», status atualizado para ..., descrição atualizada. (modificado por «ator»)` — lista só o que mudou; sem mudanças, `Atividade "«label»" atualizada.` |

A nota de edição **não** reusa a última transição (repetiria
"bloqueada/enviada..." em edições); o status só entra na nota se de fato mudou.

### 4.6 Closed é terminal

Antes de qualquer PUT, a sync faz `GET /Ticket/{id}`; `status == 6` → return.
Uma vez fechado (pela aprovação **ou manualmente no helpdesk**), a sync retorna
sem PUT nem followup — o ticket fechado é terminal (ver §8).

### 4.7 Atividade removida do plano

`cleanup_deleted_activity` ([sync.py](idac_drd/integrations/sync.py)): só em
releases ACTIVE/COMPLETED; se o ticket existe e não está fechado, registra
`Atividade "«label»" removida do plano — ticket encerrado.` e fecha com
`status=6` (o followup vem **antes** do close). O mesmo cleanup fecha a issue
GitHub (`state_reason="not_planned"`).

## 5. Resolução do responsável → GLPI

`ExternalIdentity.glpi_id` ([users/models.py](idac_drd/users/models.py),
migration 0002) — resolução local, sem chamada de API na hora da sync. Seed
inicial via fixture `identities.yaml` (vale só para instalação nova; num banco
existente, preencher via admin — `loaddata` com pk duplicado falha). O id se
verifica no GLPI em Administração → Usuários (ex.: rodrigo = 38). Vazio →
warning no log e ticket sem atribuição.

## 6. Configuração

`.env`: `GLPI_ENABLED=True`, `GLPI_API_URL` (https obrigatório — credenciais
viajam em texto plano caso contrário), `GLPI_USER`, `GLPI_PASSWORD`,
`GLPI_APP_TOKEN`.

## 7. Diagnóstico

`python manage.py check_integrations` chama `GlpiClient.check` (`getMyEntities`):
SKIP com `GLPI_ENABLED=False`, exit 1 se credenciais ou API falharem, `glpi: OK`
caso contrário.

Testes automatizados do comportamento descrito acima:
[test_glpi.py](idac_drd/integrations/tests/test_glpi.py) e
[test_sync.py](idac_drd/integrations/tests/test_sync.py).

## 8. Limitações

A integração **não** faz o seguinte (comportamento deliberado do código atual):

- Soluções automáticas (ITILSolution).
- Reabertura de tickets `closed` (inclui fechamento manual no helpdesk).
- Fallback de nota por append no `content` (usa ITILFollowup).
- Vínculo do ticket na UI do dashboard (link clicável).
