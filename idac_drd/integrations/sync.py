"""Sync automática de atividades ↔ GitHub issues e GLPI tickets.

Uma atividade de uma release em execução (ACTIVE) espelha-se em:
  - issue GitHub em ``activity.github_repo`` (criada se não existir; fechada
    quando a atividade conclui, reaberta se o status voltar a andar);
  - ticket GLPI (criado quando a atividade fica disponível — todo; atividades
    bloqueadas nunca geram ticket, o executor é atribuído na execução, o status
    acompanha a atividade e cada mudança registra nota na timeline).

Best-effort por design: qualquer falha de API é logada (warning) e nunca
quebra o fluxo do app — a integração é um efeito colateral opcional.
Gate duplo: release ACTIVE/COMPLETED e flags GH_ENABLED/GLPI_ENABLED.

Status do ticket GLPI (padrão da API): 1=New, 2=Processing, 3=Processing
(planned), 4=Pending, 5=Solved, 6=Closed. Issues GitHub só conhecem
open/closed — todo/in_progress/blocked mapeiam para open.
"""

import logging
import time
import unicodedata
from html import escape

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from idac_drd.integrations._base import IntegrationAPIError
from idac_drd.integrations.github import DEFAULT_REPO, ORG, SOFTWARE_PROJECT_NUMBER, _github_client
from idac_drd.integrations.glpi import GlpiAPIError, _glpi_client
from idac_drd.workflow.models import Activity, DataRelease

logger = logging.getLogger(__name__)

GLPI_STATUS = {
    Activity.Status.TODO: 1,
    Activity.Status.IN_PROGRESS: 2,
    Activity.Status.BLOCKED: 4,
    Activity.Status.IN_REVIEW: 4,  # GLPI não distingue "aguardando": Pending
    Activity.Status.DONE: 6,  # aprovação fecha o ticket (closed); sem solução automática
}

# Nome (por substring, case-insensitive) da opção do campo Status do Project V2
# que representa cada status do dashboard. As opções reais têm emoji como
# prefixo ("🔖 To do") — o lookup casa o nome sem depender do emoji.
GITHUB_STATUS_HINTS = {
    Activity.Status.TODO: "to do",
    Activity.Status.IN_PROGRESS: "in progress",
    Activity.Status.BLOCKED: "blocked",
    Activity.Status.IN_REVIEW: "in review",
    Activity.Status.DONE: "done",
}

# Defaults dos campos single-select do board aplicados na criação do item no
# projeto (priority=medium). Nomes normalizados — o board real usa emoji:
# '🏕 Medium' casa com "medium".
DEFAULT_PROJECT_FIELDS = {"priority": "medium"}

# Cache por processo dos campos single-select do projeto
# (project_id, {campo: (field_id, opções)}) — evita uma query GraphQL por transição.
_PROJECT_CACHE: dict = {"ts": 0.0, "data": None}
_PROJECT_TTL_SECONDS = 60


def sync_activity(activity: Activity, actor=None) -> None:
    """Cria/atualiza issue GitHub + ticket GLPI da atividade (best-effort).

    No-op silencioso quando a release não está em execução ou a integração
    está desabilitada; falhas de API são logadas. Nunca levanta. ``actor``
    (quem fez a mudança) alimenta a nota do ticket quando não há transição.
    """
    # COMPLETED entra no gate: a transição final (que aprova a última activity)
    # marca a release completed ANTES da sync agendada rodar — sem isso, o
    # ticket/issue da atividade final nunca fechariam.
    if activity.release.status not in (DataRelease.Status.ACTIVE, DataRelease.Status.COMPLETED):
        return
    _sync_github(activity)
    _sync_glpi(activity, actor)


def _resolve_repo(repo: str) -> str:
    """Normaliza "owner/repo": nome pelado (select do frontend) assume a org."""
    if "/" in repo:
        return repo
    return f"{ORG}/{repo}"


def _sync_github(activity: Activity) -> None:
    if not settings.GH_ENABLED:
        return
    if not activity.github_repo:
        logger.info(
            "Activity %s (%s) has no GitHub repo — using default %s",
            activity.key,
            activity.release.slug,
            DEFAULT_REPO,
        )
    repo = _resolve_repo(activity.github_repo or DEFAULT_REPO)  # "owner/repo"
    owner, repo_name = repo.split("/", 1)
    if owner != ORG:
        # o token de serviço só opera na org — repo fora dela seria abuso da credencial
        logger.warning(
            "Activity %s (%s): repo %r is outside org %r — no issue created",
            activity.key,
            activity.release.slug,
            repo,
            ORG,
        )
        return
    try:
        client = _github_client()
        assignee_handle = _github_assignee_handle(activity)
        assignee_fields = {"assignees": [assignee_handle]} if assignee_handle else {}
        body = _issue_body(activity)
        content_changed = body != activity.github_issue_content
        if not activity.github_issue_number:
            # paridade com o GLPI: bloqueada não gera issue — ela nasce quando
            # a atividade fica disponível (desbloqueio dispara a sync)
            if activity.status == Activity.Status.BLOCKED:
                return
            # issue recém-criada já nasce aberta — sem PATCH nesta passada
            # mesmo título do ticket GLPI — paridade entre as duas ferramentas
            issue = client.create_issue(
                owner,
                repo_name,
                title=_ticket_name(activity),
                body=body,
                assignees=[assignee_handle] if assignee_handle else None,
            )
            Activity.objects.filter(pk=activity.pk).update(
                github_issue_number=issue["number"],
                github_issue_node_id=issue.get("node_id", ""),
                github_issue_content=body,
            )
            activity.refresh_from_db()
        else:
            fields = dict(assignee_fields)
            if content_changed:
                fields["title"] = _ticket_name(activity)
                fields["body"] = body
            if activity.status == Activity.Status.DONE:
                fields["state"] = "closed"
                fields["state_reason"] = "completed"
            else:
                # PATCH idempotente: garante o issue aberto (reabre se foi
                # concluído e a atividade voltou a andar).
                fields["state"] = "open"
            client.update_issue(owner, repo_name, activity.github_issue_number, **fields)
            if content_changed:
                # snapshot do que escrevemos — comparações futuras só veem o
                # que mudou de fato (espelha o glpi_ticket_content)
                Activity.objects.filter(pk=activity.pk).update(github_issue_content=body)
        if activity.github_issue_node_id:
            _sync_project_fields(client, activity)
    except Exception as exc:  # noqa: BLE001 — best-effort: falha de integração nunca quebra o fluxo
        logger.warning("GitHub sync failed for activity %s: %s", activity.key, exc)


def _github_assignee_handle(activity: Activity) -> str | None:
    """GitHub handle do executor (ExternalIdentity.github_handle), ou None.

    Sem executor: não mexe no assignee da issue. Executor sem github_handle:
    warning e a issue fica sem assignee (espelha o GLPI sem glpi_id).
    """
    if activity.assignee is None:
        return None
    if not activity.assignee.github_handle:
        logger.warning(
            "Activity %s (%s): assignee has no github_handle — issue not assigned",
            activity.key,
            activity.release.slug,
        )
        return None
    return activity.assignee.github_handle


def _sync_project_fields(client, activity: Activity) -> None:
    """Adiciona a issue ao Project V2 e alinha Status, Área e Size (best-effort).

    Independente do issue open/closed: o projeto é o alinhamento de status do
    dashboard. Sem acesso ao projeto (scope/erro), o item é pulado — a issue e
    o ticket continuam existindo. Área/Size só são gravados quando a activity
    tem valor — remoção do campo não limpa o valor no projeto. Na criação do
    item, DEFAULT_PROJECT_FIELDS aplica os defaults do board (priority=medium)
    — mudanças manuais no board não são sobrescritas nas syncs seguintes.
    """
    try:
        project_id, fields = _project_single_select_fields(client)
        if not fields:
            return  # sem acesso ao projeto (scope/erro) — item não é criado
        item_id = activity.github_project_item_id
        if not item_id:
            item_id = client.add_project_item(project_id, activity.github_issue_node_id)
            Activity.objects.filter(pk=activity.pk).update(github_project_item_id=item_id)
            activity.refresh_from_db()
            # defaults do board só na criação do item; campo ausente no board
            # é pulado em silêncio (o default passa a valer se o campo surgir)
            for name, value in DEFAULT_PROJECT_FIELDS.items():
                field = fields.get(name)
                if not field:
                    continue
                option_id = _match_option(field[1], value)
                if option_id is None:
                    logger.warning(
                        "Activity %s (%s): no %s option matches default %r (options: %s)",
                        activity.key,
                        activity.release.slug,
                        name,
                        value,
                        list(field[1]),
                    )
                    continue
                client.set_project_item_status(project_id, item_id, field[0], option_id)
        for name, (field_id, option_ids) in fields.items():
            option_id = _project_field_value(name, option_ids, activity)
            if option_id is None:
                continue
            client.set_project_item_status(project_id, item_id, field_id, option_id)
    except Exception as exc:  # noqa: BLE001 — best-effort: o item no projeto é um extra
        logger.warning("GitHub project sync failed for activity %s: %s", activity.key, exc)


def _project_single_select_fields(client) -> tuple[str, dict[str, tuple[str, dict]]]:
    """(project_id, {nome normalizado: (field_id, {opção: option_id})}) — cacheado."""
    now = time.time()
    if _PROJECT_CACHE["data"] is None or now - _PROJECT_CACHE["ts"] > _PROJECT_TTL_SECONDS:
        _PROJECT_CACHE["data"] = client.project_single_select_fields(ORG, SOFTWARE_PROJECT_NUMBER)
        _PROJECT_CACHE["ts"] = now
    return _PROJECT_CACHE["data"]


def _match_option(option_ids: dict, source: str) -> str | None:
    """Option_id cujo nome normalizado casa com ``source`` (None = não existe)."""
    target = _normalize(source)
    for option, option_id in option_ids.items():
        if _normalize(option) == target:
            return option_id
    return None


def _project_field_value(name: str, option_ids: dict, activity: Activity) -> str | None:
    """Option_id do campo single-select correspondente à activity (None = pular)."""
    if name == "status":
        return _status_option_id(option_ids, activity.status)
    source = {"area": activity.area, "size": activity.size}.get(name)
    if not source:
        return None  # activity sem valor — não mexe no campo do projeto
    option_id = _match_option(option_ids, source)
    if option_id is None:
        logger.warning(
            "Activity %s (%s): no %s option matches %r (options: %s)",
            activity.key,
            activity.release.slug,
            name,
            source,
            list(option_ids),
        )
    return option_id


def _normalize(text: str) -> str:
    """Minúsculas sem acentos nem emoji — "🏕 Medium" → "medium" (padrão dos nomes)."""
    return unicodedata.normalize("NFD", text.lower()).encode("ascii", "ignore").decode().strip()


def _status_option_id(option_ids: dict, status: str) -> str | None:
    hint = GITHUB_STATUS_HINTS.get(status)
    if not hint:
        return None
    for name, option_id in option_ids.items():
        if hint in name.lower():
            return option_id
    return None


def _sync_glpi(activity: Activity, actor=None) -> None:
    if not settings.GLPI_ENABLED:
        return
    try:
        client = _glpi_client()
        if not activity.glpi_ticket_id:
            # criação quando a atividade fica disponível (todo) — atividades
            # bloqueadas nunca geram ticket (não polui o helpdesk)
            if activity.status == Activity.Status.BLOCKED:
                return
            body = _ticket_body(activity)
            ticket = client.create_ticket(name=_ticket_name(activity), content=body)
            Activity.objects.filter(pk=activity.pk).update(glpi_ticket_id=ticket["id"], glpi_ticket_content=body)
            activity.refresh_from_db()
            # continua a passada: atribui executor e ajusta o status do ticket novo

        ticket = client.get_ticket(activity.glpi_ticket_id)
        if ticket["status"] == 6:
            # closed é terminal: nada mais é espelhado para este ticket
            return

        # 1) executor — só em execução. Atribui o novo, remove quem saiu
        #    (re-atribuir o mesmo usuário dispara notificações em vão no GLPI;
        #    desatribuir no dashboard precisa espelhar no ticket)
        assigned = False
        if activity.status == Activity.Status.IN_PROGRESS:
            ticket_users = client.get_ticket_users(activity.glpi_ticket_id)
            assign_entries = [u for u in ticket_users if u.get("type") == 2]
            if activity.assignee is None:
                for entry in assign_entries:
                    client.unassign_ticket(activity.glpi_ticket_id, entry["id"])
                assigned = bool(assign_entries)
            elif activity.assignee.glpi_id is None:
                logger.warning(
                    "Activity %s (%s): assignee has no glpi_id — ticket not assigned",
                    activity.key,
                    activity.release.slug,
                )
            else:
                if activity.assignee.glpi_id not in {u["users_id"] for u in assign_entries}:
                    client.assign_ticket(activity.glpi_ticket_id, activity.assignee.glpi_id)
                    assigned = True
                # troca de executor: remove quem deixou de ser executor
                for entry in assign_entries:
                    if entry["users_id"] != activity.assignee.glpi_id:
                        client.unassign_ticket(activity.glpi_ticket_id, entry["id"])
                        assigned = True

        # 2) status + conteúdo — só se difere do atual (PUT idempotente)
        changes = _ticket_changes(activity, ticket)
        fields: dict = {}
        if "status" in changes:
            fields["status"] = GLPI_STATUS[activity.status]
        if "título" in changes:
            fields["name"] = _ticket_name(activity)
        if any(name in changes for name in ("descrição", "objetivos", "notas")):
            fields["content"] = _ticket_body(activity)
        if "motivo" in changes or (fields and activity.status in (Activity.Status.BLOCKED, Activity.Status.IN_REVIEW)):
            fields["pending_reason"] = _pending_reason(activity)

        # 3) descrição no body do que aconteceu (timeline do ticket)
        if fields or assigned:
            transition = activity.transitions.order_by("-id").first()
            if "status" not in changes:
                # edição: a nota descreve os campos alterados — não reusa a
                # última transição (repetiria "bloqueada/enviada..." em edições)
                transition = None
            note = _transition_note(activity, transition, actor, assigned, changes)
            if fields.get("status") == 6:
                # fecha o ticket por último: followup em ticket fechado exige o
                # right "Add followup to closed tickets" no GLPI
                client.add_followup(activity.glpi_ticket_id, note)
                client.update_ticket(activity.glpi_ticket_id, **fields)
            else:
                client.update_ticket(activity.glpi_ticket_id, **fields)
                client.add_followup(activity.glpi_ticket_id, note)
            if "content" in fields:
                # snapshot do que escrevemos — comparações futuras ignoram a
                # normalização que o GLPI possa aplicar no armazenamento
                Activity.objects.filter(pk=activity.pk).update(glpi_ticket_content=fields["content"])
    except (GlpiAPIError, IntegrationAPIError, ImproperlyConfigured, Exception) as exc:  # noqa: BLE001
        logger.warning("GLPI sync failed for activity %s: %s", activity.key, exc)


def _ticket_name(activity: Activity) -> str:
    """Título do ticket: RELEASE - STEP: Activity (contexto no helpdesk)."""
    return f"{activity.release.name} - {activity.step.label}: {activity.label}"


def _pending_reason(activity: Activity) -> str:
    if activity.status == Activity.Status.BLOCKED:
        return activity.blocked_reason or "Atividade bloqueada"
    return f'Aguardando revisão da atividade "{activity.label}"'


def _assignee_name(activity: Activity) -> str:
    if activity.assignee is None:
        return "não atribuído"
    return activity.assignee.name or activity.assignee.email or str(activity.assignee.glpi_id)


def _author_name(actor) -> str:
    """Nome de quem fez a mudança (transição registra o ator; edição passa o request.user)."""
    if actor is None:
        return ""
    return getattr(actor, "name", "") or getattr(actor, "username", "") or ""


def _transition_note(activity: Activity, transition, actor=None, assigned=False, changes=None) -> str:
    """Descrição do que aconteceu, registrada na timeline do ticket.

    Sem prefixo de origem: o título do ticket (RELEASE - STEP) já indica que a
    nota vem do Dashboard. Autor: ator da transição quando existe; senão quem
    disparou a sync (edição). Edições sem transição nomeiam os campos que
    mudaram (``changes``) — o status só entra na nota se de fato mudou.
    """
    label = activity.label
    author = _author_name(transition.actor if transition is not None and transition.actor else actor)
    if transition is None:
        # edição de campos: autor "modificou" o que está no ticket
        by = f" (modificado por {author})" if author else ""
        items: list[str] = []
        if assigned:
            if activity.assignee is None:
                items.append("executor removido")
            else:
                items.append(f"executor alterado para {_assignee_name(activity)}")
        if changes:
            items.extend(
                _change_label(name, activity)
                for name in ("título", "descrição", "objetivos", "notas", "motivo", "status")
                if name in changes
            )
        if not items:
            return f'Atividade "{label}" atualizada.{by}'
        return f'Atividade "{label}" — ' + ", ".join(items) + f".{by}"
    # transição de status: o autor "requisitou" a mudança
    by = f" (requisitado por {author})" if author else ""
    to = transition.to_status
    if to == Activity.Status.BLOCKED:
        reason = activity.blocked_reason or transition.comment or "sem motivo informado"
        return f'Atividade "{label}" bloqueada: {reason}.{by}'
    if to == Activity.Status.IN_REVIEW:
        return f'Atividade "{label}" enviada para revisão — aguardando aprovação.{by}'
    if to == Activity.Status.DONE:
        if transition.from_status == Activity.Status.IN_REVIEW:
            return f'Atividade "{label}" aprovada e concluída.{by}'
        return f'Atividade "{label}" concluída.{by}'
    if to == Activity.Status.IN_PROGRESS and transition.from_status == Activity.Status.IN_REVIEW:
        # HTML mínimo: o GLPI renderiza parágrafos e negrito na timeline
        reason = escape(transition.comment or "sem motivo informado")
        return f"<p><strong>Revisão recusada</strong></p><p>{reason}. Voltou para execução.{by}</p>"
    if to == Activity.Status.IN_PROGRESS:
        return f'Atividade "{label}" iniciada — executor: {_assignee_name(activity)}.{by}'
    return f'Atividade "{label}" passou para {activity.get_status_display()}.{by}'


def _objective_line(line: str) -> str:
    """Linha com marcação manual ([x]/[ ]) é preservada; linha solta vira tarefa aberta."""
    if line[:3].lower() in ("[x]", "[ ]"):
        return f"- {line}"
    return f"- [ ] {line}"


def _objectives_block(activity: Activity) -> list[str]:
    goals = [line.strip() for line in activity.objectives.splitlines() if line.strip()]
    if not goals:
        return []
    return ["", "**Objetivos:**"] + [_objective_line(goal) for goal in goals]


def _issue_body(activity: Activity) -> str:
    # abre com o nome composto: a issue tem só o label como título, o corpo
    # carrega o contexto de release/step; markdown é nativo no GitHub
    parts = [_ticket_name(activity)]
    if activity.description:
        parts.append("")
        parts.append(activity.description)
    parts.extend(_objectives_block(activity))
    if activity.notes:
        parts.append("")
        parts.append("**Notas:**")
        parts.append(activity.notes)
    return "\n".join(parts)


def _ticket_sections(activity: Activity) -> dict[str, str]:
    """Seções do corpo do ticket em HTML mínimo, na ordem do corpo.

    O GLPI renderiza parágrafos e negrito. Sem o nome composto: o título do
    ticket já é RELEASE - STEP: Activity, não precisa repetir. Descrição,
    objetivos e notas entram quando existem. As seções nomeadas alimentam a
    nota da timeline (o que mudou nesta sync).
    """
    sections: dict[str, str] = {}
    if activity.description:
        sections["descrição"] = f"<p>{escape(activity.description)}</p>"
    goals = [line.strip() for line in activity.objectives.splitlines() if line.strip()]
    if goals:
        sections["objetivos"] = "<p><strong>Objetivos:</strong></p>\n" + "\n".join(
            f"<p>{escape(_objective_line(goal))}</p>" for goal in goals
        )
    if activity.notes:
        sections["notas"] = f"<p><strong>Notas:</strong></p>\n<p>{escape(activity.notes)}</p>"
    return sections


# corpo mínimo quando a atividade não tem descrição/objetivos/notas: a API do
# GLPI pode rejeitar content em branco e aí a criação falharia e re-tentaria
# em toda sync
_FALLBACK_BODY = "<p>Sem descrição.</p>"


def _ticket_body(activity: Activity) -> str:
    return "\n".join(_ticket_sections(activity).values()) or _FALLBACK_BODY


# Cabeçalhos das seções no corpo do ticket — detectam seções removidas
_SECTION_HEADERS = {
    "objetivos": "<strong>Objetivos:</strong>",
    "notas": "<strong>Notas:</strong>",
}


def _strip_named_section(content: str, header: str) -> str:
    """Remove a seção ``header`` (de <p><strong>header</strong></p> até a próxima
    seção nomeada ou o fim) — o que sobra fora das seções é a descrição."""
    marker = f"<p><strong>{header}</strong></p>"
    idx = content.find(marker)
    if idx == -1:
        return content
    tail = content[idx + len(marker) :]
    next_header = tail.find("<p><strong>")
    if next_header == -1:
        # seção é a última do content: remove até o fim
        tail = ""
    else:
        # remove o conteúdo da seção, mantendo da próxima seção em diante
        tail = tail[next_header:]
    return (content[:idx] + tail).strip()


def _ticket_changes(activity: Activity, ticket: dict) -> list[str]:
    """Campos que o ticket ainda não reflete — o que esta sync vai escrever.

    Compara o estado atual da atividade com o snapshot que o ticket carrega
    (última sync): título, seções do corpo, status e motivo de pendência.
    Alimenta a nota da timeline e o PUT idempotente.

    Conteúdo: compara contra ``activity.glpi_ticket_content`` (o que nós
    gravamos) e não contra o GET — o GLPI pode devolver o HTML normalizado e a
    comparação acharia mudança em toda sync. NULL (legado) compara contra o GET.
    """
    changes: list[str] = []
    if ticket.get("name") != _ticket_name(activity):
        changes.append("título")
    if activity.glpi_ticket_content is not None:
        old_content = activity.glpi_ticket_content
    else:
        old_content = ticket.get("content") or ""
    sections = _ticket_sections(activity)
    for name, block in sections.items():
        if name != "descrição" and block not in old_content:
            changes.append(name)
    for name, header in _SECTION_HEADERS.items():
        if name not in sections and header in old_content:
            changes.append(name)
    # descrição não tem header: compara o que resta do content fora das seções
    # nomeadas — cobre edição e remoção (a seção some do body novo). Sem
    # nenhuma seção o body novo é o fallback, não vazio.
    old_rest = old_content
    for header in ("Objetivos:", "Notas:"):
        old_rest = _strip_named_section(old_rest, header)
    if old_rest == _FALLBACK_BODY:
        # fallback não é descrição real: corpo antigo sem descrição nenhuma
        old_rest = ""
    new_rest = sections.get("descrição") or ""
    if old_rest != new_rest:
        changes.append("descrição")
    if ticket.get("status") != GLPI_STATUS[activity.status]:
        changes.append("status")
    if activity.status in (Activity.Status.BLOCKED, Activity.Status.IN_REVIEW):
        # só quando a API devolve o campo: se nunca vier, não há como comparar
        # (e não queremos PUT + nota em toda sync)
        expected = _pending_reason(activity)
        current = ticket.get("pending_reason")
        if current is not None and current != expected:
            changes.append("motivo")
    return changes


def _change_label(name: str, activity: Activity) -> str:
    """Descrição de um campo alterado, para a nota da timeline."""
    if name == "título":
        return f'título atualizado para "{_ticket_name(activity)}"'
    if name == "status":
        return f"status atualizado para {activity.get_status_display()}"
    if name == "motivo":
        if activity.status == Activity.Status.BLOCKED:
            return "motivo do bloqueio atualizado"
        return "motivo de pendência atualizado"
    return {
        "descrição": "descrição atualizada",
        "objetivos": "objetivos atualizados",
        "notas": "notas atualizadas",
    }[name]


def cleanup_deleted_activity(release_status, github_repo, github_issue_number, glpi_ticket_id, label) -> None:
    """Fecha a issue GitHub e o ticket GLPI de uma atividade removida do rascunho.

    Best-effort: a atividade já não existe — falha vira warning e nada mais.
    Só age em releases em execução (antes do start não há issue/ticket).
    """
    if release_status not in (DataRelease.Status.ACTIVE, DataRelease.Status.COMPLETED):
        return
    github_repo = _resolve_repo(github_repo or DEFAULT_REPO)
    if settings.GH_ENABLED and github_issue_number and github_repo and "/" in github_repo:
        owner, repo_name = github_repo.split("/", 1)
        if owner == ORG:
            try:
                _github_client().update_issue(
                    owner, repo_name, github_issue_number, state="closed", state_reason="not_planned"
                )
            except Exception as exc:  # noqa: BLE001 — best-effort pós-delete
                logger.warning("GitHub cleanup failed for deleted activity: %s", exc)
    if settings.GLPI_ENABLED and glpi_ticket_id:
        try:
            client = _glpi_client()
            ticket = client.get_ticket(glpi_ticket_id)
            if ticket["status"] != 6:
                client.add_followup(glpi_ticket_id, f'Atividade "{label}" removida do rascunho — ticket encerrado.')
                client.update_ticket(glpi_ticket_id, status=6)
        except Exception as exc:  # noqa: BLE001 — best-effort pós-delete
            logger.warning("GLPI cleanup failed for deleted activity: %s", exc)
