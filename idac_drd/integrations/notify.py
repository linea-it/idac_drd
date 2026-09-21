"""Notificações de fluxo (best-effort, fora do caminho crítico).

Política: quando a ação depende de um responsável, avisá-lo no canal
SLACK_CHANNEL_ID com menção; a DM (via ``slack_id``) é só o fallback quando
não há canal. Copy PT-BR por superfície: canal em 3ª pessoa com <@slack_id>
quando há recipient; DM em 2ª pessoa (sem menção, já é privada). CTA é link
mrkdwn absoluto (<url|label>) quando SITE_URL está configurado; sem SITE_URL,
o CTA é omitido (nunca imprimir path relativo).

Threads por step: no início da release, cada step com atividades ganha uma
mensagem âncora no canal (notify_release_started); os eventos de atividade
(notify_ready/review/rejection/blocked) viram replies na thread do step
(``ReleaseStep.slack_thread_ts``). Falha na âncora degrada para mensagem
top-level. A conclusão (notify_release_complete) é mensagem de topo (marco
final).

Inerte a menos que SLACK_ENABLED. Falhas só logam, nunca levantam.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from idac_drd.integrations.slack import _slack_client
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep

logger = logging.getLogger(__name__)


def _mention(recipient: str | None) -> str:
    """Prefixo de menção para o canal; vazio sem slack_id."""
    return f"<@{recipient}> " if recipient else ""


def _release_link(release: DataRelease, label: str) -> str:
    """CTA mrkdwn do Slack; vazio quando SITE_URL não está configurado."""
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    if not base:
        return ""
    return f"<{base}/releases/{release.slug}/|{label}>"


def _headline(activity: Activity) -> str:
    return f"{activity.release.name} · *{activity.label}*"


def _join(head: str, body: str, link: str) -> str:
    parts = [head, body]
    if link:
        parts.append(link)
    return "\n".join(parts)


def _post_or_dm(channel_text: str, dm_text: str, recipient: str | None, thread_ts: str | None = None) -> None:
    """Canal é o destino primário (texto 3ª pessoa + @); DM só como fallback
    quando não há canal configurado. ``thread_ts`` posta no canal como reply."""
    client = _slack_client()
    if settings.SLACK_CHANNEL_ID:
        client.post_to_channel(settings.SLACK_CHANNEL_ID, channel_text, thread_ts=thread_ts)
    elif recipient:
        client.send_dm_to_user(recipient, dm_text)


def _step_anchor_text(step: ReleaseStep) -> str:
    """Texto da âncora da thread do step: título + atividades + CTA."""
    head = f"*{step.release.name}* · {step.label}"
    activities = "\n".join(f"• {a.label}" for a in step.activities.all().order_by("order", "id"))
    parts = [head]
    if activities:
        parts.append(activities)
    link = _release_link(step.release, "Ver DPN")
    if link:
        parts.append(link)
    return "\n".join(parts)


def _post_step_anchor(client, step: ReleaseStep) -> str | None:
    """Posta a âncora do step no canal e grava o ts (dedup por update atômico).

    Retorna o ts da thread (novo ou existente) ou None em falha.
    """
    resp = client.post_to_channel(settings.SLACK_CHANNEL_ID, _step_anchor_text(step))
    ts = resp.get("ts")
    if not ts:
        logger.warning("Slack anchor response without ts for step %s", step.id)
        return None
    updated = ReleaseStep.objects.filter(pk=step.pk, slack_thread_ts="").update(slack_thread_ts=ts)
    if updated:
        step.slack_thread_ts = ts
        return ts
    # outro post venceu a corrida — reusa o ts já gravado
    current = ReleaseStep.objects.only("slack_thread_ts").get(pk=step.pk)
    return current.slack_thread_ts or ts


def _ensure_step_thread(step: ReleaseStep) -> str | None:
    """Retorna o ts da thread do step, criando a âncora se necessário.

    Sempre re-fetch do ts por pk (instâncias em memória podem estar stale
    depois de ``filter().update()``). Falha → None (o reply cai top-level;
    melhor perder o threading que perder o evento).
    """
    current = ReleaseStep.objects.only("slack_thread_ts").get(pk=step.pk)
    if current.slack_thread_ts:
        return current.slack_thread_ts
    try:
        return _post_step_anchor(_slack_client(), step)
    except Exception:
        logger.warning("Slack anchor failed for step %s", step.id, exc_info=True)
        return None


def notify_ready(activity: Activity) -> None:
    """Avisa que ``activity`` está pronta para iniciar (ação do assignee).

    Disparos: desbloqueio de pré-requisitos, criação em release em execução
    e início da release. Canal com menção ao assignee (via ``slack_id``);
    DM ao assignee só como fallback sem canal. Sem ambos, o aviso é pulado.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return

    assignee = activity.assignee
    recipient = assignee.slack_id if assignee else None
    if not settings.SLACK_CHANNEL_ID and not recipient:
        return

    head = _headline(activity)
    link = _release_link(activity.release, "Abrir a atividade")
    channel_text = _join(head, f"{_mention(recipient)}esta atividade está pronta para você começar.", link)
    dm_text = _join(head, "sua atividade está pronta para você começar.", link)
    try:
        thread_ts = _ensure_step_thread(activity.step) if settings.SLACK_CHANNEL_ID else None
        _post_or_dm(channel_text, dm_text, recipient, thread_ts)
    except Exception:
        logger.warning("Slack ready notification failed for activity %s", activity.id, exc_info=True)


def notify_stale_todo(activity: Activity) -> bool:
    """Lembrete: a atividade segue em todo sem ter sido iniciada.

    Mesmos gates e destino de ``notify_ready``. Copy distinta para não parecer
    o aviso inicial de novo. Repete a cada STALE_TODO_REMIND_HOURS enquanto
    permanecer em todo.
    """
    if not settings.SLACK_ENABLED:
        return False
    if activity.release.status != DataRelease.Status.ACTIVE:
        return False

    assignee = activity.assignee
    recipient = assignee.slack_id if assignee else None
    if not settings.SLACK_CHANNEL_ID and not recipient:
        return False

    head = _headline(activity)
    link = _release_link(activity.release, "Abrir a atividade")
    channel_text = _join(
        head, f":alert: {_mention(recipient)}esta atividade ainda está disponível e não foi iniciada.", link
    )
    dm_text = _join(head, ":alert: sua atividade ainda está disponível e não foi iniciada.", link)
    try:
        thread_ts = _ensure_step_thread(activity.step) if settings.SLACK_CHANNEL_ID else None
        _post_or_dm(channel_text, dm_text, recipient, thread_ts)
        return True
    except Exception:
        logger.warning("Slack stale-todo notification failed for activity %s", activity.id, exc_info=True)
        return False


def remind_stale_todos() -> int:
    """Envia o lembrete para TODOs prontos há pelo menos STALE_TODO_REMIND_HOURS.

    Só atividades de release ACTIVE, ainda em todo, com ``ready_at`` vencido.
    Repete a cada intervalo enquanto continuar em todo: o próximo ping é
    ``stale_todo_notified_at`` + intervalo (ou ``ready_at`` se nunca avisou).
    Pré-requisitos pendentes são ignorados. O update atômico evita duplicata
    se o comando rodar em paralelo. Retorna quantos avisos foram enviados.
    """
    hours = getattr(settings, "STALE_TODO_REMIND_HOURS", 12)
    if hours <= 0 or not settings.SLACK_ENABLED:
        return 0

    now = timezone.now()
    cutoff = now - timedelta(hours=hours)
    due = Q(stale_todo_notified_at__isnull=True) | Q(stale_todo_notified_at__lte=cutoff)
    candidates = (
        Activity.objects.filter(
            status=Activity.Status.TODO,
            release__status=DataRelease.Status.ACTIVE,
            ready_at__isnull=False,
            ready_at__lte=cutoff,
        )
        .filter(due)
        .select_related("release", "step", "assignee")
        .order_by("id")
    )

    sent = 0
    for activity in candidates:
        if not activity.prerequisites_met():
            continue
        # #30: não lembrar quem já está com alguma atividade em execução
        if (
            activity.assignee_id
            and Activity.objects.filter(
                assignee_id=activity.assignee_id,
                status=Activity.Status.IN_PROGRESS,
            ).exists()
        ):
            continue
        claimed = (
            Activity.objects.filter(pk=activity.pk, status=Activity.Status.TODO)
            .filter(due)
            .update(stale_todo_notified_at=now)
        )
        if not claimed:
            continue
        if notify_stale_todo(activity):
            sent += 1
        else:
            Activity.objects.filter(pk=activity.pk, stale_todo_notified_at=now).update(
                stale_todo_notified_at=activity.stale_todo_notified_at
            )
    return sent


def notify_review(activity: Activity) -> None:
    """Avisa que ``activity`` aguarda review.

    Qualquer pessoa pode aprovar. O canal menciona os assignees das
    atividades que dependem desta (quem é desbloqueado pelo done); DM a
    um deles só como fallback sem canal. Sem dependentes com slack_id,
    só o canal, sem menção; sem canal e sem DM-alvo o aviso é pulado.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return

    dependents = list(activity.dependents.select_related("assignee").order_by("order", "id"))
    slack_ids = [dep.assignee.slack_id for dep in dependents if dep.assignee and dep.assignee.slack_id]
    recipient = slack_ids[0] if slack_ids else None
    if not settings.SLACK_CHANNEL_ID and not recipient:
        return

    head = _headline(activity)
    link = _release_link(activity.release, "Revisar entrega")
    mentions = "".join(_mention(sid) for sid in slack_ids)
    if dependents:
        labels = ", ".join(f"*{dep.label}*" for dep in dependents)
        body_channel = f"{mentions}a entrega espera revisão. Aprovar libera {labels}."
        body_dm = f"a entrega espera revisão. Aprovar libera {labels}."
    else:
        body_channel = "Qualquer pessoa pode aprovar esta entrega."
        body_dm = body_channel
    try:
        thread_ts = _ensure_step_thread(activity.step) if settings.SLACK_CHANNEL_ID else None
        _post_or_dm(_join(head, body_channel, link), _join(head, body_dm, link), recipient, thread_ts)
    except Exception:
        logger.warning("Slack review notification failed for activity %s", activity.id, exc_info=True)


def notify_rejection(activity: Activity, comment: str, reviewer: str = "") -> None:
    """Avisa que a entrega de ``activity`` foi devolvida (ação do executor).

    Canal com menção ao assignee (quem precisa corrigir); DM a ele só como
    fallback sem canal. ``reviewer`` é o username de quem rejeitou
    (informativo); ``comment`` é o motivo, obrigatório na rejeição. Sem
    assignee com slack_id, só o canal sem menção; sem canal e sem DM-alvo,
    o aviso é pulado.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return

    assignee = activity.assignee
    recipient = assignee.slack_id if assignee else None
    if not settings.SLACK_CHANNEL_ID and not recipient:
        return

    head = _headline(activity)
    by = f"\nRevisada por {reviewer}." if reviewer else ""
    body_channel = (
        f"{_mention(recipient)}a revisão devolveu a atividade.{by}\n"
        f"*Motivo:* {comment}\n"
        f"Corrija e envie de novo."
    )
    body_dm = f"a revisão devolveu sua atividade.{by}\n" f"*Motivo:* {comment}\n" f"Corrija e envie de novo."
    link = _release_link(activity.release, "Corrigir e reenviar")
    try:
        thread_ts = _ensure_step_thread(activity.step) if settings.SLACK_CHANNEL_ID else None
        _post_or_dm(_join(head, body_channel, link), _join(head, body_dm, link), recipient, thread_ts)
    except Exception:
        logger.warning("Slack rejection notification failed for activity %s", activity.id, exc_info=True)


def notify_blocked(activity: Activity, reason: str, actor: str = "") -> None:
    """Avisa que ``activity`` foi bloqueada manualmente (motivo obrigatório).

    Só bloqueio operacional (não o auto-block de pré-requisitos). Canal com
    menção ao assignee; DM a ele só como fallback sem canal. ``reason`` é o
    ``blocked_reason``/comentário; ``actor`` é o username de quem bloqueou.
    """
    if not settings.SLACK_ENABLED:
        return
    if activity.release.status != DataRelease.Status.ACTIVE:
        return
    if not (reason or "").strip():
        return

    assignee = activity.assignee
    recipient = assignee.slack_id if assignee else None
    if not settings.SLACK_CHANNEL_ID and not recipient:
        return

    head = _headline(activity)
    by = f"\nBloqueada por {actor}." if actor else ""
    body_channel = f"{_mention(recipient)}a atividade foi bloqueada.{by}\n*Motivo:* {reason}"
    body_dm = f"sua atividade foi bloqueada.{by}\n*Motivo:* {reason}"
    link = _release_link(activity.release, "Abrir a atividade")
    try:
        thread_ts = _ensure_step_thread(activity.step) if settings.SLACK_CHANNEL_ID else None
        _post_or_dm(_join(head, body_channel, link), _join(head, body_dm, link), recipient, thread_ts)
    except Exception:
        logger.warning("Slack blocked notification failed for activity %s", activity.id, exc_info=True)


def notify_release_started(release: DataRelease) -> None:
    """Abre as threads dos steps com atividades (aviso proativo no canal).

    Uma mensagem âncora por step, com as atividades do step; eventos
    seguintes viram replies na thread. Gate: SLACK_ENABLED + canal.
    Disparo: start_release.
    """
    if not settings.SLACK_ENABLED:
        return
    if not settings.SLACK_CHANNEL_ID:
        return

    try:
        for step in release.steps.all():
            if step.activities.exists():
                _ensure_step_thread(step)
    except Exception:
        logger.warning("Slack start notification failed for release %s", release.id, exc_info=True)


def notify_release_complete(release: DataRelease) -> None:
    """Avisa no canal que a release foi concluída (aviso de time).

    Gate: SLACK_ENABLED + canal configurado. A release está COMPLETED — não
    se aplica o gate de ACTIVE dos avisos de atividade. Sem canal, skip (não
    há um único responsável para DM).
    """
    if not settings.SLACK_ENABLED:
        return
    if not settings.SLACK_CHANNEL_ID:
        return

    link = _release_link(release, "Ver DPN")
    text = f"*{release.name}* concluído.\nTodas as atividades foram aprovadas."
    if link:
        text += f"\n{link}"
    try:
        _slack_client().post_to_channel(settings.SLACK_CHANNEL_ID, text)
    except Exception:
        logger.warning("Slack completion notification failed for release %s", release.id, exc_info=True)
