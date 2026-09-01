# Hooks Slack no fluxo da Activity

Comportamento atual das notificações Slack no fluxo de atividades. Estrutura
espelhada em [glpi-hooks.md](glpi-hooks.md).

---

## 1. Visão geral

O Slack é **só-notificação** (sem eventos, botões ou interação). A regra de
negócio: quando a próxima ação depende de um responsável, avisá-lo **no canal**
(`SLACK_CHANNEL_ID`) com menção `<@slack_id>`; a DM é só o fallback quando não
há canal configurado. Falha da âncora degrada para mensagem top-level; falha
de API loga warning — nunca levanta, nunca quebra o fluxo.

Dois módulos:

- [slack.py](idac_drd/integrations/slack.py) — cliente Web API (stateless,
  best-effort, inerte sem `SLACK_ENABLED`).
- [notify.py](idac_drd/integrations/notify.py) — superfícies de notificação do
  fluxo, com a copy PT-BR.

O agendamento fica em [services.py](idac_drd/workflow/services.py)
(`_notify_*_later` via `transaction.on_commit` + `_safe`, mesmo padrão da sync
GitHub/GLPI) — o HTTP roda depois do commit, e a ordem FIFO dos callbacks
garante que as âncoras das threads saiam antes dos replies no `start_release`.

## 2. Cliente Slack ([slack.py](idac_drd/integrations/slack.py))

| Método | Chamada | Uso |
|---|---|---|
| `lookup_user_by_email` | `users.lookupByEmail` | email SAML → user id |
| `send_dm(email, text)` | lookup + `conversations.open` + `chat.postMessage` | DM a um email (abre a DM sozinho; o usuário **não precisa instalar o app**) |
| `send_dm_to_user(user_id, text)` | `conversations.open` + `chat.postMessage` | DM a um id já resolvido |
| `post_to_channel(channel_id, text, thread_ts=None)` | `chat.postMessage` | mensagem no canal; `thread_ts` posta como reply |
| `check` | `auth.test` | smoke test do `check_integrations` |
| `post_slack_message` | — | canal quando `SLACK_CHANNEL_ID`; senão DM do `SLACK_DEV_USER_ID` (fallback dev) |

Pegadinhas validadas:

- **Body form-urlencoded (`data=`)** — vários métodos (`conversations.*`)
  rejeitam `json=` com `invalid_arguments`/`missing_charset`.
- Erro de API chega como HTTP 200 com `ok: false` — o erro real e o
  `response_metadata.messages` (campo/escopo exato) entram no `SlackAPIError`.
- Menção real é `<@USER_ID>` (não `@nome`); `as_user` foi removido da API —
  o bot posta como bot.
- Bot **IDAC-BR Data Release** (`U0BQB3EV2TB`), workspace LIneA. Escopos:
  `chat:write`, `users:read`, `im:write`, `channels:read`, `users:read.email`
  (este último é o que permite resolver emails; sem ele `users.list` volta
  sem `profile.email`).

## 3. Superfícies de notificação ([notify.py](idac_drd/integrations/notify.py))

Estrutura padrão das mensagens: headline `{release.name} · *{label}*` + corpo
+ CTA (link mrkdwn absoluto `<url|label>`, omitido sem `SITE_URL` — nunca
imprimir path relativo).

| Evento (disparo) | Função | Destinatário | Texto do corpo |
|---|---|---|---|
| início da release (`start_release`) | `notify_release_started` | canal, **top-level** | âncora por step (ver §4) |
| atividade pronta para iniciar (`start_release`, `add_activity` em release ativa, desbloqueio manual `blocked`→`todo`, desbloqueio automático de pré-requisitos) | `notify_ready` | canal + menção ao assignee; DM fallback | `«@»esta atividade está pronta para você começar.` / `sua atividade está pronta para você começar.` — CTA "Abrir a atividade" |
| todo parado (`remind_stale_todos`, ainda em `todo` 12h após `ready_at` / último ping) | `notify_stale_todo` | mesmo destino de `notify_ready` | `:alert: «@»esta atividade ainda está disponível e não foi iniciada.` / `:alert: sua atividade ainda está disponível e não foi iniciada.` — CTA "Abrir a atividade" |
| enviada à revisão (`todo`→`in_review`) | `notify_review` | canal + menção aos **assignees das atividades dependentes**; DM fallback | `«@»a entrega espera revisão. Aprovar libera *«dependentes»*.` — CTA "Revisar entrega" |
| rejeição (`in_review`→`in_progress` com motivo) | `notify_rejection` | canal + menção ao executor; DM fallback | `«@»a revisão devolveu a atividade.` + `Revisada por «reviewer».` + `*Motivo:* «comment»` + `Corrija e envie de novo.` — CTA "Corrigir e reenviar" |
| release concluída (aprovação da última atividade) | `notify_release_complete` | canal, **top-level** | `*«release»* concluído. Todas as atividades foram aprovadas.` — CTA "Ver DPN" |

Detalhes por superfície:

- **Quem aprova / `notify_review`**: qualquer pessoa autenticada pode
  aprovar pelo board. O aviso menciona os assignees das **atividades que
  dependem desta** (aprovar desbloqueia essas). Sem dependentes, sem
  assignee ou sem `slack_id` → só o canal, sem menção ("Qualquer pessoa
  pode aprovar esta entrega."); sem canal e sem DM-alvo, o aviso é
  pulado. Cada `in_review` notifica de novo (inclusive após rejeição).
- **`notify_rejection`**: `comment` é obrigatório na rejeição e entra no corpo.
  Sem executor com `slack_id` → só o canal sem menção.
- **`notify_ready`**: sem assignee com `slack_id` → só o canal; sem canal e sem
  slack_id → pulado. Grava `Activity.ready_at` (relógio do lembrete).
- **`notify_stale_todo`**: enquanto a atividade segue em `todo` numa release
  ACTIVE com pré-requisitos ok, o aviso se **repete a cada 12h** (primeiro
  ping 12h após `ready_at`; os seguintes 12h após `stale_todo_notified_at`).
  Voltar a `todo` zera o relógio. Job: `python manage.py remind_stale_todos`
  (serviço `remind` no compose de produção, a cada 5 min).
  `STALE_TODO_REMIND_HOURS` (default 12; `0` desliga).
- **Copy por superfície**: canal em 3ª pessoa com `<@slack_id>`; DM em 2ª
  pessoa **sem menção** (já é privada).
- **Não notifica**: a entrada em `in_progress` em si (o aviso "pronta" já saiu
  em todo; a atribuição acontece pelo board) e o bloqueio manual (quem bloqueia
  assume a pendência).

### 3.1 Gates

- `SLACK_ENABLED` (default `False`) — inerte sem a flag.
- Eventos de atividade exigem `release.status == ACTIVE` (notify_ready/review/
  rejection). `notify_release_complete` não checa status (a release está
  COMPLETED; o disparo só vem da última aprovação).
- Canal como destino primário; DM só sem canal; sem canal e sem DM-alvo, o
  aviso é pulado.

## 4. Threads por step

No início da release, cada step **com atividades** ganha uma mensagem âncora
top-level no canal:

```
*{release.name}* · {step.label}
• {atividade 1}
• {atividade 2}
Ver DPN
```

O `ts` da âncora é gravado em `ReleaseStep.slack_thread_ts` (migration 0003,
preenchida **só** pelo sync de notificação, nunca via API). Os eventos de
atividade (§3) viram **replies** nessa thread (`thread_ts`).

- **Âncora preguiçosa**: sem `slack_thread_ts`, o primeiro evento do step posta
  a âncora e o reply na thread recém-criada.
- **Dedup**: a gravação é um `update` atômico (`slack_thread_ts=""` → ts); se
  outro post venceu a corrida, o ts já gravado é reutilizado (a âncora extra
  não é gravada).
- **Falha da âncora** (exceção ou resposta sem `ts`) → o evento ainda sai,
  como mensagem de topo (melhor perder o threading que perder o evento).
- **Conclusão é marco final**: `notify_release_complete` é top-level, não
  reply.

## 5. Configuração

`.env`: `SLACK_ENABLED=True`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` (canal do
projeto: `C06JSRLF2JU`; o bot precisa ser convidado: `/invite @IDAC-BR Data
Release`), `SITE_URL` (libera os CTAs). Fallback dev: sem canal, `post_slack_message`
cai para DM do `SLACK_DEV_USER_ID`; no fluxo de notify, DM é só via
`ExternalIdentity.slack_id` de quem precisa agir.

Resolução de destinatário: `ExternalIdentity.slack_id`
([users/models.py](idac_drd/users/models.py), mesma tabela do `glpi_id`) —
menções no canal e DMs vêm daqui; sem `slack_id` não há chamada de API para
resolver na hora. Seed via fixture `identities.yaml` + admin.

Smoke test: `python manage.py check_integrations` (SLACK SKIP/OK/FAIL).

## 6. Diagnóstico

`python manage.py check_integrations` chama `SlackClient.check` (`auth.test`):
SKIP com `SLACK_ENABLED=False`, exit 1 se token ou API falharem, `slack: OK` caso
contrário.

Testes automatizados do comportamento descrito acima:
[test_notify.py](idac_drd/integrations/tests/test_notify.py) e
[test_slack.py](idac_drd/integrations/tests/test_slack.py).

## 7. Limitações

A integração **não** faz o seguinte (comportamento deliberado do código atual):

- Eventos/interação do Slack (botões, slash commands, respostas a mensagens).
- DM como destino primário (o canal é o padrão; DM só no fallback dev).
- Menção/aviso de bloqueio manual e de entrada em execução.
