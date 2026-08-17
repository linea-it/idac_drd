"""Notificações de fluxo (best-effort, fora do caminho crítico).

Hoje: aviso de review por Slack quando uma atividade entra em ``in_review``.
O aprovador natural (assignee da próxima activity do mesmo step) recebe um DM —
aprovar destrava o próprio trabalho dele (pull, estilo kanban).

Inerte a menos que SLACK_ENABLED. Nunca levanta: falhas só logam.
"""

import logging

from django.conf import settings

from idac_drd.integrations.slack import _slack_client
from idac_drd.workflow.models import Activity, DataRelease

logger = logging.getLogger(__name__)


def _board_url(activity: Activity) -> str:
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}/releases/{activity.release.slug}/"


def notify_review(activity: Activity) -> None:
    """Avisa o aprovador natural de ``activity`` que ela aguarda review.

    Aprovador: assignee da próxima activity do mesmo step (``next_in_step``),
    resolvido por ``slack_id``. Sem aprovador específico (última do step,
    próxima sem assignee ou sem slack_id) o aviso é pulado — staff/qualquer
    pessoa seguem podendo aprovar pelo board.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return

    next_activity = activity.next_in_step()
    assignee = next_activity.assignee if next_activity else None
    if not assignee or not assignee.slack_id:
        return

    text = (
        f"👀 *Review needed: {activity.label}* — {activity.release.name}\n\n"
        f"*{activity.label}* was delivered for review. Approving it unlocks "
        f"your next activity: *{next_activity.label}*.\n\n"
        f"{_board_url(activity)}"
    )
    try:
        _slack_client().send_dm_to_user(assignee.slack_id, text)
    except Exception:
        logger.warning("Slack review notification failed for activity %s", activity.id, exc_info=True)


def notify_rejection(activity: Activity, comment: str, reviewer: str = "") -> None:
    """Avisa o executor de ``activity`` que a entrega foi rejeitada.

    Destinatário: o próprio assignee (quem precisa corrigir). Sem assignee
    com slack_id o aviso é pulado. ``reviewer`` é o username de quem rejeitou
    (informativo); ``comment`` é o motivo, obrigatório na rejeição.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return

    assignee = activity.assignee
    if not assignee or not assignee.slack_id:
        return

    by = f" by {reviewer}" if reviewer else ""
    text = (
        f"↩️ *Rejected{by}: {activity.label}* — {activity.release.name}\n\n"
        f"*{activity.label}* was sent back to in progress.\n\n"
        f"*Reason:* {comment}\n\n"
        f"{_board_url(activity)}"
    )
    try:
        _slack_client().send_dm_to_user(assignee.slack_id, text)
    except Exception:
        logger.warning("Slack rejection notification failed for activity %s", activity.id, exc_info=True)
