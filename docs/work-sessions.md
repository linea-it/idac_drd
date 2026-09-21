# Play/pause e sessões de trabalho (effort / FTE)

Comportamento atual do timer de esforço nas atividades (issue #30). Estrutura
espelhada em [slack-hooks.md](slack-hooks.md) e [glpi-hooks.md](glpi-hooks.md).

---

## 1. Visão geral

O **status** da activity (`todo`, `in_progress`, `in_review`, `done`, `blocked`)
continua sendo o workflow operacional. O **effort** (tempo efetivo para FTE) é
outra dimensão: intervalos play→pause gravados em `ActivityWorkSession`.

Regras de negócio:

- no máximo **uma sessão aberta por assignee** (global, todas as releases);
- no máximo **uma sessão aberta por activity**;
- play numa activity **auto-pausa** a sessão anterior do mesmo assignee
  (`end_reason=play_switch`);
- **não há auto-pause por idle** — sessão esquecida aberta continua contando
  até pause explícito ou saída de execução (review / blocked / done / reassign);
- play/pause só o **assignee** (match `User.email` ↔ `ExternalIdentity.email`,
  case-insensitive) ou **superusuário**.

Dois módulos principais:

- [models.py](idac_drd/workflow/models.py) — `ActivityWorkSession`;
- [services.py](idac_drd/workflow/services.py) — `play_activity`, `pause_activity`,
  `open_work_session`, `can_control_timer`, `activity_effort_seconds`.

API: `POST /api/activities/{id}/play/` e `POST /api/activities/{id}/pause/`
([views.py](idac_drd/workflow/api/views.py)).

## 2. Modelo `ActivityWorkSession`

| Campo | Significado |
|---|---|
| `activity` | FK da activity |
| `assignee` | snapshot do `ExternalIdentity` no play (não segue mudança futura) |
| `started_at` | início do intervalo |
| `ended_at` | `NULL` = sessão aberta (playing) |
| `end_reason` | `pause`, `play_switch`, `review`, `blocked`, `done`, `reassign`, `admin`, `manual` |
| `actor` | usuário logado que abriu/fechou (opcional) |

Constraints (PostgreSQL):

- `uniq_open_work_session_per_assignee` — no máximo um `(assignee)` com
  `ended_at IS NULL`;
- `uniq_open_work_session_per_activity` — no máximo um `(activity)` com
  `ended_at IS NULL`.

Migration: `workflow.0008_activityworksession`.

## 3. Ciclo de vida do timer

| Evento | Status workflow | Sessão |
|---|---|---|
| Play em `todo` (prereqs ok) | → `in_progress` | abre sessão |
| Play em `in_progress` pausada | permanece | abre sessão |
| Play noutra activity do mesmo assignee | outra → `in_progress` se estava `todo` | fecha a anterior (`play_switch`); abre na nova |
| Pause | permanece `in_progress` | fecha (`pause`) |
| Status → `in_progress` (sem Play) | transição | **não** abre sessão — Play (ou effort manual) grava FTE |
| Effort manual (`POST …/effort/`) | permanece `in_progress` | cria sessão **fechada** (`manual`) — só se ainda não há nenhuma |
| → `in_review` | só de `in_progress` **e** com ≥1 sessão (effort > 0 ou sessão aberta/fechada) | fecha sessão aberta (`review`) |
| → `blocked` / `done` / volta a `todo` | transição normal | fecha sessão aberta |
| Rejeição `in_review` → `in_progress` | volta | **não** abre sozinho — exige Play |
| Troca / remoção de assignee | — | fecha (`reassign`) |

Play sem assignee → erro. Play sem permissão → erro
("Only the assignee or a superuser…"). Enviar a review sem effort → erro
("Record effort with Play or add it manually…").

### Effort manual (esqueceu o Play)

`POST /api/activities/{id}/effort/` com `{"minutes": 45}`.

Só vale quando **ainda não há sessão** nesta activity: mesma permissão do
Play, status `in_progress`, assignee definido, `minutes` ∈ (0, 1440].
Cria uma sessão fechada com `end_reason=manual` (intervalo `[now−minutes, now]`).
No drawer: campo Minutes + "Add effort" quando In progress sem effort.

## 4. API

### `POST /api/activities/{id}/play/`

Autenticado. Body vazio.

Resposta: serializer da activity + campo extra:

```json
{
  "id": 1,
  "status": "in_progress",
  "is_playing": true,
  "playing_since": "2026-09-21T21:00:00Z",
  "effort_seconds": 12.5,
  "duration_seconds": null,
  "paused_activities": [
    { "id": 2, "label": "Outra activity" }
  ]
}
```

`paused_activities` lista o que o auto-switch pausou (toast na UI).

### `POST /api/activities/{id}/pause/`

Autenticado. Fecha a sessão aberta; status permanece `in_progress`.

### Campos no `ActivitySerializer`

| Campo | Significado |
|---|---|
| `duration_seconds` | **Cycle** (calendário): `completed_at − started_at` se ambos existem; senão `null` |
| `effort_seconds` | **Effort**: soma das sessões (inclui sessão aberta até `now`) |
| `is_playing` | existe sessão com `ended_at IS NULL` nesta activity |
| `playing_since` | `started_at` da sessão aberta, se houver |

## 5. Métricas: cycle vs effort

São duas métricas diferentes e **ambas** entram no relatório Markdown do board
([report.js](frontend/src/report.js)):

| Métrica | Fonte | Uso |
|---|---|---|
| Cycle (`duration_seconds`) | wall-clock `started_at` → `completed_at` | lead/cycle time, gargalos de calendário |
| Effort (`effort_seconds`) | soma de `ActivityWorkSession` | FTE / tempo efetivo com play ligado |

O relatório mostra cycle e effort no resumo executivo, na tabela por step, na
timeline de cada activity e no workload por assignee (com nota explicativa).

## 6. UI

- **Kanban / drawer / DAG**: botão play/pause (fora do `CardActionArea` no
  Kanban — não abre o drawer).
- Chip de status: timer ligado → **In Progress**; `in_progress` sem sessão →
  **Paused** (filtros facetados continuam usando `displayStatus` cru =
  `in_progress`).
- Banner “You're on: …” quando o email do login bate com o assignee da sessão
  aberta (inclui effort no banner).
- Toast ao auto-switch: `Paused: «label»`.
- Tempo de effort **não** aparece no card (só drawer / banner / relatório) —
  evita aparência de vigilância no board.
- Botão some (com mensagem) se login sem email, email ≠ assignee, ou sem
  assignee — salvo superuser.
- Templates Django e `frontend/index.html` (dev Vite) expõem
  `data-user-email`, `data-is-superuser`, `data-is-staff`.

## 7. Lembrete Slack (cruzamento com #30)

`remind_stale_todos` **não** envia lembrete de todo parado se o assignee já
tem qualquer activity em `in_progress`. Detalhe em
[slack-hooks.md](slack-hooks.md) (`notify_stale_todo`).

## 8. O que não faz parte deste desenho

- FTE fracionário por contagem de cards (0,5 / 0,33);
- status Kanban `paused` separado no banco (pause é só timer);
- auto-pause por tempo ocioso;
- NiFi / jobs automáticos gerando sessões humanas.
