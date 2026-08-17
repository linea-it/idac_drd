"""Sync automática de atividades ↔ GitHub issues e GLPI tickets.

Uma atividade de uma release em execução (ACTIVE) espelha-se em:
  - issue GitHub em ``activity.github_repo`` (criada se não existir; fechada
    quando a atividade conclui, reaberta se o status voltar a andar);
  - ticket GLPI (criado se não existir; status acompanha a atividade).

Best-effort por design: qualquer falha de API é logada (warning) e nunca
quebra o fluxo do app — a integração é um efeito colateral opcional.
Gate duplo: release ACTIVE e flags GH_ENABLED/GLPI_ENABLED.

Status do ticket GLPI (padrão da API): 1=New, 2=Processing, 3=Processing
(planned), 4=Pending, 5=Solved, 6=Closed. Issues GitHub só conhecem
open/closed — todo/in_progress/blocked mapeiam para open.
"""

import logging
import time

from django.conf import settings

from idac_drd.integrations.github import ORG, SOFTWARE_PROJECT_NUMBER, _github_client
from idac_drd.integrations.glpi import _glpi_client
from idac_drd.workflow.models import Activity, DataRelease

logger = logging.getLogger(__name__)

GLPI_STATUS = {
    Activity.Status.TODO: 1,
    Activity.Status.IN_PROGRESS: 2,
    Activity.Status.BLOCKED: 4,
    Activity.Status.IN_REVIEW: 4,  # GLPI não distingue "aguardando": Pending
    Activity.Status.DONE: 5,
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

# Cache por processo do field Status do projeto (id do projeto, id do campo,
# opções) — evita uma query GraphQL a cada transição.
_PROJECT_CACHE: dict = {"ts": 0.0, "data": None}
_PROJECT_TTL_SECONDS = 60


def sync_activity(activity: Activity) -> None:
    """Cria/atualiza issue GitHub + ticket GLPI da atividade (best-effort).

    No-op silencioso quando a release não está em execução ou a integração
    está desabilitada; falhas de API são logadas. Nunca levanta.
    """
    if activity.release.status != DataRelease.Status.ACTIVE:
        return
    _sync_github(activity)
    _sync_glpi(activity)


def _sync_github(activity: Activity) -> None:
    if not settings.GH_ENABLED:
        return
    repo = activity.github_repo  # "owner/repo"
    if not repo or "/" not in repo:
        logger.warning("Activity %s (%s) has no GitHub repo — no issue created", activity.key, activity.release.slug)
        return
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
        if not activity.github_issue_number:
            # issue recém-criada já nasce aberta — sem PATCH nesta passada
            issue = client.create_issue(
                owner,
                repo_name,
                title=activity.label,
                body=_issue_body(activity),
            )
            Activity.objects.filter(pk=activity.pk).update(
                github_issue_number=issue["number"],
                github_issue_node_id=issue.get("node_id", ""),
            )
            activity.refresh_from_db()
        elif activity.status == Activity.Status.DONE:
            client.update_issue(
                owner, repo_name, activity.github_issue_number, state="closed", state_reason="completed"
            )
        else:
            # PATCH idempotente: garante o issue aberto (reabre se foi concluído
            # e a atividade voltou a andar).
            client.update_issue(owner, repo_name, activity.github_issue_number, state="open")
        if activity.github_issue_node_id:
            _sync_project_status(client, activity)
    except Exception as exc:  # noqa: BLE001 — best-effort: falha de integração nunca quebra o fluxo
        logger.warning("GitHub sync failed for activity %s: %s", activity.key, exc)


def _sync_project_status(client, activity: Activity) -> None:
    """Adiciona a issue ao Project V2 e atualiza o campo Status (best-effort).

    Independente do issue open/closed: o projeto é o alinhamento de status do
    dashboard. Sem acesso ao projeto (scope/erro), o item é pulado — a issue e
    o ticket continuam existindo.
    """
    try:
        project_id, field_id, option_ids = _project_status_field(client)
        option_id = _status_option_id(option_ids, activity.status)
        if option_id is None:
            logger.warning(
                "No Project V2 status option matches activity status %r (options: %s)",
                activity.status,
                list(option_ids),
            )
            return
        item_id = activity.github_project_item_id
        if not item_id:
            item_id = client.add_project_item(project_id, activity.github_issue_node_id)
            Activity.objects.filter(pk=activity.pk).update(github_project_item_id=item_id)
            activity.refresh_from_db()
        client.set_project_item_status(project_id, item_id, field_id, option_id)
    except Exception as exc:  # noqa: BLE001 — best-effort: o item no projeto é um extra
        logger.warning("GitHub project sync failed for activity %s: %s", activity.key, exc)


def _project_status_field(client) -> tuple[str, str, dict]:
    now = time.time()
    if _PROJECT_CACHE["data"] is None or now - _PROJECT_CACHE["ts"] > _PROJECT_TTL_SECONDS:
        _PROJECT_CACHE["data"] = client.project_field(ORG, SOFTWARE_PROJECT_NUMBER)
        _PROJECT_CACHE["ts"] = now
    return _PROJECT_CACHE["data"]


def _status_option_id(option_ids: dict, status: str) -> str | None:
    hint = GITHUB_STATUS_HINTS.get(status)
    if not hint:
        return None
    for name, option_id in option_ids.items():
        if hint in name.lower():
            return option_id
    return None


def _sync_glpi(activity: Activity) -> None:
    if not settings.GLPI_ENABLED:
        return
    try:
        client = _glpi_client()
        if not activity.glpi_ticket_id:
            ticket = client.create_ticket(name=activity.label, content=_ticket_body(activity))
            Activity.objects.filter(pk=activity.pk).update(glpi_ticket_id=ticket["id"])
        else:
            client.update_ticket(activity.glpi_ticket_id, status=GLPI_STATUS[activity.status])
    except (GlpiAPIError, IntegrationAPIError, ImproperlyConfigured, Exception) as exc:  # noqa: BLE001
        logger.warning("GLPI sync failed for activity %s: %s", activity.key, exc)


def _objectives_block(activity: Activity) -> list[str]:
    goals = [line.strip() for line in activity.objectives.splitlines() if line.strip()]
    if not goals:
        return []
    return ["", "**Objectives:**"] + [f"- [ ] {goal}" for goal in goals]


def _issue_body(activity: Activity) -> str:
    parts = [f"Automated issue for activity **{activity.label}** (release **{activity.release.name}**)."]
    if activity.description:
        parts.append("")
        parts.append(activity.description)
    parts.extend(_objectives_block(activity))
    return "\n".join(parts)


def _ticket_body(activity: Activity) -> str:
    parts = [f"Automated ticket for activity **{activity.label}** (release **{activity.release.name}**)."]
    if activity.description:
        parts.append("")
        parts.append(activity.description)
    parts.extend(_objectives_block(activity))
    return "\n".join(parts)
