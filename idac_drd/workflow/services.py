import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import F, Max
from django.utils import timezone
from django.utils.text import slugify

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, ActivityTransition, ActivityWorkSession, DataRelease, ReleaseStep

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


def _assert_mutable(release: DataRelease) -> None:
    if release.is_readonly:
        raise WorkflowError("This release is archived, so it can't be changed.")


def can_control_timer(activity: Activity, actor) -> bool:
    """Play/pause: assignee (email) ou superusuário."""
    if actor is None:
        return False
    if getattr(actor, "is_superuser", False):
        return True
    assignee = activity.assignee
    if not assignee or not assignee.email:
        return False
    user_email = (getattr(actor, "email", None) or "").strip().lower()
    if not user_email:
        return False
    return user_email == assignee.email.strip().lower()


def activity_effort_seconds(activity: Activity, *, now=None) -> float:
    """Soma das sessões de trabalho (inclui sessão aberta até ``now``)."""
    now = now or timezone.now()
    total = 0.0
    sessions = getattr(activity, "_prefetched_objects_cache", {}).get("work_sessions")
    if sessions is None:
        sessions = activity.work_sessions.all()
    for session in sessions:
        end = session.ended_at or now
        total += (end - session.started_at).total_seconds()
    return total


def close_open_sessions_for_assignee(
    assignee_id: int,
    *,
    reason: str,
    actor=None,
    except_activity_id: int | None = None,
) -> int:
    """Fecha sessões abertas do assignee. Retorna quantas fechou."""
    now = timezone.now()
    qs = ActivityWorkSession.objects.filter(assignee_id=assignee_id, ended_at__isnull=True)
    if except_activity_id is not None:
        qs = qs.exclude(activity_id=except_activity_id)
    return qs.update(ended_at=now, end_reason=reason, actor=actor)


def close_open_session_for_activity(activity: Activity, *, reason: str, actor=None) -> int:
    """Fecha a sessão aberta desta activity, se houver."""
    now = timezone.now()
    return ActivityWorkSession.objects.filter(activity=activity, ended_at__isnull=True).update(
        ended_at=now, end_reason=reason, actor=actor
    )


def open_work_session(activity: Activity, *, actor=None) -> tuple[ActivityWorkSession | None, list[Activity]]:
    """Abre sessão nesta activity (pausa qualquer outra do mesmo assignee).

    Retorna ``(session, paused_activities)``. Sem assignee → ``(None, [])``.
    Sessão já aberta nesta activity → no-op ``(existing, [])``.
    """
    if not activity.assignee_id:
        return None, []
    existing = ActivityWorkSession.objects.filter(activity=activity, ended_at__isnull=True).first()
    if existing:
        return existing, []
    open_others = list(
        ActivityWorkSession.objects.filter(assignee_id=activity.assignee_id, ended_at__isnull=True)
        .exclude(activity_id=activity.id)
        .select_related("activity")
    )
    paused = [s.activity for s in open_others]
    close_open_sessions_for_assignee(
        activity.assignee_id,
        reason=ActivityWorkSession.EndReason.PLAY_SWITCH,
        actor=actor,
        except_activity_id=activity.id,
    )
    session = ActivityWorkSession.objects.create(
        activity=activity,
        assignee_id=activity.assignee_id,
        started_at=timezone.now(),
        actor=actor,
    )
    return session, paused


def play_activity(activity: Activity, *, actor=None) -> tuple[Activity, list[Activity]]:
    """Inicia/retoma o timer: todo→in_progress se preciso; uma sessão aberta por assignee.

    Retorna ``(activity, paused_activities)`` — as que foram auto-pausadas no switch.
    """
    _assert_mutable(activity.release)
    if activity.release.status == DataRelease.Status.DRAFT:
        raise WorkflowError("Start the release before changing activity status.")
    if not activity.assignee_id:
        raise WorkflowError("Assign someone before starting the timer.")
    if not can_control_timer(activity, actor):
        raise WorkflowError("Only the assignee or a superuser can start the timer.")
    if activity.status not in (Activity.Status.TODO, Activity.Status.IN_PROGRESS):
        raise WorkflowError("Play only from To do or In progress.")
    if not activity.prerequisites_met():
        pending = list(activity.depends_on.exclude(status=Activity.Status.DONE).values_list("label", flat=True))
        raise WorkflowError(
            "Finish these first: " + ", ".join(pending) if pending else "Finish the prerequisites first."
        )

    with transaction.atomic():
        if activity.status == Activity.Status.TODO:
            transition_activity(activity, to_status=Activity.Status.IN_PROGRESS, actor=actor)
            activity.refresh_from_db()
        _, paused = open_work_session(activity, actor=actor)
    return activity, paused


def pause_activity(activity: Activity, *, actor=None) -> Activity:
    """Pausa o timer; status permanece in_progress."""
    _assert_mutable(activity.release)
    if activity.release.status == DataRelease.Status.DRAFT:
        raise WorkflowError("Start the release before changing activity status.")
    if not can_control_timer(activity, actor):
        raise WorkflowError("Only the assignee or a superuser can pause the timer.")
    if activity.status != Activity.Status.IN_PROGRESS:
        raise WorkflowError("Pause only while In progress.")
    close_open_session_for_activity(activity, reason=ActivityWorkSession.EndReason.PAUSE, actor=actor)
    return activity


# teto anti-typo: 24h (esqueceu o Play, não um sprint inteiro de uma vez)
_MAX_MANUAL_EFFORT_MINUTES = 24 * 60


def record_manual_effort(activity: Activity, *, minutes: float, actor=None) -> Activity:
    """Registra effort fechado quando a pessoa esqueceu o Play (só se ainda não há sessão)."""
    _assert_mutable(activity.release)
    if activity.release.status == DataRelease.Status.DRAFT:
        raise WorkflowError("Start the release before changing activity status.")
    if not activity.assignee_id:
        raise WorkflowError("Assign someone before recording effort.")
    if not can_control_timer(activity, actor):
        raise WorkflowError("Only the assignee or a superuser can record effort.")
    if activity.status != Activity.Status.IN_PROGRESS:
        raise WorkflowError("Record manual effort only while In progress.")
    if activity.work_sessions.exists():
        raise WorkflowError("Effort already recorded — use Play/Pause to add more time.")
    try:
        minutes = float(minutes)
    except (TypeError, ValueError) as exc:
        raise WorkflowError("Minutes must be a number.") from exc
    if minutes <= 0:
        raise WorkflowError("Minutes must be greater than zero.")
    if minutes > _MAX_MANUAL_EFFORT_MINUTES:
        raise WorkflowError(f"Minutes cannot exceed {_MAX_MANUAL_EFFORT_MINUTES} (24h).")

    now = timezone.now()
    seconds = minutes * 60
    ActivityWorkSession.objects.create(
        activity=activity,
        assignee_id=activity.assignee_id,
        started_at=now - timedelta(seconds=seconds),
        ended_at=now,
        end_reason=ActivityWorkSession.EndReason.MANUAL,
        actor=actor if getattr(actor, "pk", None) else None,
    )
    return activity


def _safe(call, *args):
    """Chama o callback de integração sem deixar exceção escapar.

    Uma falha não derruba as tarefas seguintes nem vira 500. Erro vira log.
    """
    try:
        call(*args)
    except Exception:  # noqa: BLE001 — pós-commit, erro só loga
        logger.exception("Integration callback %s failed", getattr(call, "__name__", call))


# Um worker, fila FIFO. notify_release_started entra antes dos sync/replies.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="idac-integrations")
_queue_state = threading.Condition()
_inflight = 0
# Teste segura o worker antes do corpo da tarefa; produção deixa aberto.
_run_gate = threading.Event()
_run_gate.set()


def _run_integration(fn, args):
    """Roda uma tarefa na thread do worker, com a conexão dela."""
    _run_gate.wait()
    close_old_connections()
    try:
        _safe(fn, *args)
    finally:
        close_old_connections()
        with _queue_state:
            global _inflight
            _inflight -= 1
            _queue_state.notify_all()


def _dispatch(fn, args):
    """Eager: executa na thread do commit. Senão: só enfileira."""
    if getattr(settings, "INTEGRATIONS_EAGER", False):
        _safe(fn, *args)
        return
    global _inflight
    with _queue_state:
        _inflight += 1
    _executor.submit(_run_integration, fn, args)


def _after_commit(fn, *args):
    """Agenda depois do commit. Rollback não registra callback."""
    transaction.on_commit(lambda: _dispatch(fn, args))


def hold_integrations():
    """Impede o worker de entrar na tarefa até drain_integrations()."""
    _run_gate.clear()


def drain_integrations(timeout=10):
    """Libera o worker e espera a fila FIFO esvaziar."""
    _run_gate.set()
    with _queue_state:
        if not _queue_state.wait_for(lambda: _inflight == 0, timeout):
            raise TimeoutError("integration queue did not drain")


def _sync_later(activity: Activity, *, actor=None) -> None:
    """Agenda a sync de integrações (GitHub/GLPI) para depois do commit.

    O on_commit só enfileira. As chamadas HTTP não rodam na transação nem na
    request. A sync decide se aplica (gate: release em execução + flags).
    ``actor`` vai para a nota do ticket quando não há transição.
    """
    from idac_drd.integrations.sync import sync_activity

    _after_commit(sync_activity, activity, actor)


def _mark_ready(activity: Activity) -> None:
    """Inicia o relógio quando a atividade fica disponível em TODO/ACTIVE."""
    if activity.release.status != DataRelease.Status.ACTIVE or activity.status != Activity.Status.TODO:
        return
    now = timezone.now()
    Activity.objects.filter(pk=activity.pk).update(ready_at=now, stale_todo_notified_at=None)
    activity.ready_at = now
    activity.stale_todo_notified_at = None


def _notify_ready_later(activity: Activity) -> None:
    """Agenda o aviso de "pronta para iniciar" (Slack ao assignee + canal)."""
    from idac_drd.integrations.notify import notify_ready

    _after_commit(notify_ready, activity)


def _notify_review_later(activity: Activity) -> None:
    """Agenda o aviso de review (Slack DM ao aprovador) para depois do commit.

    O callback roda fora da transação; a notificação decide se aplica
    (gate: release em execução + SLACK_ENABLED) e nunca levanta.
    """
    from idac_drd.integrations.notify import notify_review

    _after_commit(notify_review, activity)


def _notify_rejection_later(activity: Activity, comment: str, reviewer=None) -> None:
    """Agenda o aviso de rejeição (Slack DM ao executor) para depois do commit."""
    from idac_drd.integrations.notify import notify_rejection

    reviewer_name = reviewer.username if reviewer else ""
    _after_commit(notify_rejection, activity, comment, reviewer_name)


def _notify_blocked_later(activity: Activity, reason: str, actor=None) -> None:
    """Agenda o aviso de bloqueio manual (Slack canal/DM) para depois do commit."""
    from idac_drd.integrations.notify import notify_blocked

    actor_name = actor.username if actor else ""
    _after_commit(notify_blocked, activity, reason, actor_name)


def _notify_started_later(release: DataRelease) -> None:
    """Agenda o aviso de início de release (Slack no canal) para depois do commit."""
    from idac_drd.integrations.notify import notify_release_started

    _after_commit(notify_release_started, release)


def _notify_complete_later(release: DataRelease) -> None:
    """Agenda o aviso de conclusão de release (Slack no canal) para depois do commit."""
    from idac_drd.integrations.notify import notify_release_complete

    _after_commit(notify_release_complete, release)


def _strip_marks(objectives: str) -> str:
    """Colchetes [x]/[ ] são marcação de execução — a cópia nasce limpa."""
    return "\n".join(re.sub(r"^\[[x ]\]\s*", "", line) for line in (objectives or "").splitlines())


def pending_objectives(objectives: str) -> list[str]:
    """Linhas ainda não marcadas [x]. Texto sem colchete conta como pendente."""
    pending = []
    for line in (objectives or "").splitlines():
        text = line.strip()
        if not text:
            continue
        if re.match(r"^\[x\]\s*", text, flags=re.IGNORECASE):
            continue
        pending.append(re.sub(r"^\[[x ]\]\s*", "", text, flags=re.IGNORECASE))
    return pending


def _clone_structure(source_steps, source_items, target: DataRelease) -> DataRelease:
    """Copia steps + activities de uma release de origem para a release-alvo.

    Itens precisam expor step, key, label, description, objectives, order,
    mode, github_repo, area, size, assignee e depends_on. Status sempre reseta
    para todo e a marcação [x]/[ ] dos objetivos é zerada.
    """
    step_map: dict[str, ReleaseStep] = {}
    for step in source_steps.all():
        step_map[step.key] = ReleaseStep.objects.create(
            release=target,
            key=step.key,
            label=step.label,
            order=step.order,
            color=step.color,
            resources=step.resources,
        )

    item_map: dict[int, Activity] = {}
    for item in source_items.select_related("step", "assignee").all():
        item_map[item.id] = Activity.objects.create(
            release=target,
            step=step_map[item.step.key],
            key=item.key,
            label=item.label,
            description=item.description,
            objectives=_strip_marks(item.objectives),
            order=item.order,
            status=Activity.Status.TODO,
            mode=item.mode,
            github_repo=item.github_repo,
            area=item.area,
            size=item.size,
            resources=item.resources,
            assignee=item.assignee,
        )

    for item in source_items.prefetch_related("depends_on").all():
        activity = item_map[item.id]
        dep_ids = [item_map[dep.id].id for dep in item.depends_on.all() if dep.id in item_map]
        if dep_ids:
            activity.depends_on.set(dep_ids)
        _block_until_prerequisites(activity)
        # releases clonadas já em execução criam issues/tickets para cada activity
        _sync_later(activity)
    return target


@transaction.atomic
def create_draft(
    *,
    name: str,
    slug: str | None = None,
    copy_from_release: DataRelease | None = None,
) -> DataRelease:
    """Cria um draft em branco ou copiando uma release anterior.

    O draft é o objeto primário: nasce ``draft`` sem ``started_at`` e só
    sai do rascunho via ``start_release``. ``template_key`` guarda a origem
    histórica (string) quando a release copiada veio de um template.
    """
    release = DataRelease.objects.create(
        name=name,
        slug=slug or slugify(name),
        status=DataRelease.Status.DRAFT,
        template_key=(copy_from_release.template_key if copy_from_release else ""),
    )
    if copy_from_release is not None:
        _clone_structure(copy_from_release.steps.all(), copy_from_release.activities.all(), release)
    return release


def _resume_completed_release(release: DataRelease) -> None:
    """Step/atividade novos numa release completada reabrem a execução.

    Sem isso a release fica COMPLETED com trabalho novo: a sync até rodaria
    (o gate aceita COMPLETED), mas o board segue mostrando a release fechada
    e as notificações (que exigem ACTIVE) nunca são enviadas.
    """
    if release.status == DataRelease.Status.COMPLETED:
        release.status = DataRelease.Status.ACTIVE
        release.save(update_fields=["status", "updated_at"])


# Motivo automático de bloqueio por pré-requisito (prefixo; legado PT ainda desbloqueia).
_PREREQ_BLOCK_PREFIX = "Waiting on prerequisites"
_PREREQ_BLOCK_PREFIXES = (_PREREQ_BLOCK_PREFIX, "Aguardando pré-requisitos")


def _unblock_ready_dependents(activity: Activity) -> None:
    """Conclusão desbloqueia dependentes: atividades bloqueadas por pré-requisito
    (motivo automático) com todos os pré-requisitos atendidos voltam para todo —
    e a sync agenda o ticket, já que a atividade ficou disponível."""
    for dep in activity.dependents.filter(status=Activity.Status.BLOCKED):
        if dep.blocked_reason and dep.blocked_reason.startswith(_PREREQ_BLOCK_PREFIXES) and dep.prerequisites_met():
            dep.status = Activity.Status.TODO
            dep.blocked_reason = ""
            dep.save(update_fields=["status", "blocked_reason", "updated_at"])
            _sync_later(dep)
            _mark_ready(dep)
            _notify_ready_later(dep)


def _block_until_prerequisites(activity: Activity) -> None:
    """Alinha status ao estado dos pré-requisitos (mesmo critério do import).

    Pendente + todo → blocked com motivo automático. Motivo automático e
    prereqs ok → volta para todo. Bloqueio manual não é tocado.
    """
    pending = list(activity.depends_on.exclude(status=Activity.Status.DONE).values_list("label", flat=True))
    auto = bool(activity.blocked_reason) and activity.blocked_reason.startswith(_PREREQ_BLOCK_PREFIXES)
    if pending:
        if activity.status == Activity.Status.TODO or (
            activity.status == Activity.Status.BLOCKED and (auto or not activity.blocked_reason)
        ):
            activity.status = Activity.Status.BLOCKED
            activity.blocked_reason = f"{_PREREQ_BLOCK_PREFIX}: " + ", ".join(pending)
            activity.save(update_fields=["status", "blocked_reason"])
    elif auto and activity.status == Activity.Status.BLOCKED:
        activity.status = Activity.Status.TODO
        activity.blocked_reason = ""
        activity.save(update_fields=["status", "blocked_reason", "updated_at"])


def transition_activity(
    activity: Activity,
    *,
    to_status: str,
    actor=None,
    comment: str = "",
) -> Activity:
    _assert_mutable(activity.release)
    if activity.release.status == DataRelease.Status.DRAFT:
        raise WorkflowError("Start the release before changing activity status.")
    if to_status not in Activity.Status.values:
        raise WorkflowError(f"Can't set status to {to_status}.")

    if (
        to_status in (Activity.Status.IN_PROGRESS, Activity.Status.IN_REVIEW, Activity.Status.DONE)
        and not activity.prerequisites_met()
    ):
        pending = list(activity.depends_on.exclude(status=Activity.Status.DONE).values_list("label", flat=True))
        raise WorkflowError(
            "Finish these first: " + ", ".join(pending) if pending else "Finish the prerequisites first."
        )

    if to_status == Activity.Status.BLOCKED and not (activity.blocked_reason or comment):
        raise WorkflowError("Add a reason for blocking this activity.")

    from_status = activity.status
    if from_status == to_status:
        return activity

    if to_status == Activity.Status.IN_REVIEW:
        # o valor continua válido para histórico e sync; o fluxo não entra mais nele
        raise WorkflowError("Complete the activity from In progress. Review is a later activity.")
    if to_status == Activity.Status.DONE:
        # legado: quem já está in_review ainda pode concluir
        if from_status == Activity.Status.IN_REVIEW:
            pass
        elif from_status != Activity.Status.IN_PROGRESS:
            raise WorkflowError("Complete only from In progress.")
        else:
            if not activity.work_sessions.exists():
                raise WorkflowError("Record effort with Play or add it manually before completing.")
            pending = pending_objectives(activity.objectives)
            if pending:
                raise WorkflowError("Check every objective before completing: " + ", ".join(pending))
    elif to_status == Activity.Status.IN_PROGRESS and from_status == Activity.Status.IN_REVIEW:
        # legado: devolver uma atividade que ainda está in_review exige motivo
        if not comment:
            raise WorkflowError("Add a reason to reject this review.")

    now = timezone.now()
    activity.status = to_status
    if from_status == Activity.Status.BLOCKED and to_status != Activity.Status.BLOCKED:
        # saiu do bloqueio (ex.: pré-requisitos atendidos) — o motivo não vale mais
        activity.blocked_reason = ""
    if to_status == Activity.Status.IN_PROGRESS and not activity.started_at:
        activity.started_at = now
    if to_status == Activity.Status.DONE:
        activity.completed_at = now
        if not activity.started_at:
            activity.started_at = now
    activity.save()

    ActivityTransition.objects.create(
        activity=activity,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        comment=comment,
    )

    # timer: só Play abre sessão; sair de execução fecha a aberta
    if to_status == Activity.Status.IN_REVIEW:
        close_open_session_for_activity(activity, reason=ActivityWorkSession.EndReason.REVIEW, actor=actor)
    elif to_status == Activity.Status.BLOCKED:
        close_open_session_for_activity(activity, reason=ActivityWorkSession.EndReason.BLOCKED, actor=actor)
    elif to_status == Activity.Status.DONE:
        close_open_session_for_activity(activity, reason=ActivityWorkSession.EndReason.DONE, actor=actor)
    elif to_status == Activity.Status.TODO:
        close_open_session_for_activity(activity, reason=ActivityWorkSession.EndReason.PAUSE, actor=actor)

    if to_status == Activity.Status.DONE:
        _unblock_ready_dependents(activity)
    completed = sync_release_completion(activity.release)
    _sync_later(activity)
    if completed and activity.release.status == DataRelease.Status.COMPLETED:
        # fechar o ciclo: a última aprovação avisa o time (não o caminho inverso)
        _notify_complete_later(activity.release)
    if to_status == Activity.Status.IN_REVIEW:
        _notify_review_later(activity)
    elif to_status == Activity.Status.IN_PROGRESS and from_status == Activity.Status.IN_REVIEW:
        # rejeição da revisão: avisa o executor para corrigir
        _notify_rejection_later(activity, comment, actor)
    elif to_status == Activity.Status.BLOCKED:
        # bloqueio manual (auto-prereq usa _block_until_prerequisites, não esta via)
        reason = (activity.blocked_reason or comment or "").strip()
        if reason and not reason.startswith(_PREREQ_BLOCK_PREFIXES):
            _notify_blocked_later(activity, reason, actor)
    elif to_status == Activity.Status.TODO and from_status != Activity.Status.TODO:
        # desbloqueio manual (ex.: pré-requisitos já atendidos): é a vez do assignee
        _mark_ready(activity)
        _notify_ready_later(activity)
    return activity


def sync_release_completion(release: DataRelease) -> bool:
    """Marca a release como completed quando todas as atividades estão done;
    volta para active se alguma atividade deixou de estar done (releases
    arquivadas não são tocadas)."""
    all_done = not release.activities.exclude(status=Activity.Status.DONE).exists()
    target = DataRelease.Status.COMPLETED if all_done else DataRelease.Status.ACTIVE
    if release.status == DataRelease.Status.DRAFT or release.status == DataRelease.Status.ARCHIVED:
        return False
    if release.status == target:
        return False
    release.status = target
    release.save(update_fields=["status", "updated_at"])
    return True


@transaction.atomic
def add_activity(
    release: DataRelease,
    *,
    label: str,
    step: ReleaseStep,
    key: str | None = None,
    description: str = "",
    objectives: str = "",
    after: Activity | None = None,
    depends_on_ids: list[int] | None = None,
    mode: str = Activity.Mode.MANUAL,
    github_repo: str = "",
    area: str = "",
    size: str = "",
    resources: list | None = None,
    assignee: ExternalIdentity | None = None,
    link_after: bool = True,
) -> Activity:
    _assert_mutable(release)
    _resume_completed_release(release)
    if step.release_id != release.id:
        raise WorkflowError("That step isn't in this release.")

    activity_key = key or slugify(label)
    if Activity.objects.filter(release=release, key=activity_key).exists():
        activity_key = f"{activity_key}-{Activity.objects.filter(release=release).count() + 1}"

    if after:
        order = after.order + 1
    elif step.activities.exists():
        order = step.activities.order_by("-order").first().order + 1
    else:
        order = 0

    Activity.objects.filter(release=release, step=step, order__gte=order).update(order=F("order") + 1)

    activity = Activity.objects.create(
        release=release,
        step=step,
        key=activity_key,
        label=label,
        description=description,
        objectives=objectives,
        order=order,
        status=Activity.Status.TODO,
        mode=mode,
        github_repo=github_repo,
        area=area,
        size=size,
        resources=resources or [],
        assignee=assignee,
    )

    deps = []
    if after and link_after:
        deps.append(after)
    if depends_on_ids:
        deps.extend(list(Activity.objects.filter(release=release, id__in=depends_on_ids)))
    if deps:
        activity.depends_on.set({d.id for d in deps})
    _block_until_prerequisites(activity)
    _sync_later(activity)
    if activity.release.status == DataRelease.Status.ACTIVE and activity.status == Activity.Status.TODO:
        # release em execução: a atividade nova nasce pronta, mesmo sem assignee
        _mark_ready(activity)
        if activity.assignee_id:
            _notify_ready_later(activity)
    return activity


@transaction.atomic
def duplicate_activity(activity: Activity) -> Activity:
    """Cópia estrutural logo abaixo da original, sem herdar dependências.

    Reaproveita label/descrição/objetivos/recursos quando duas atividades são
    parecidas. Status sempre todo; [x] dos objetivos zera; issue/ticket, notes
    e depends_on não vêm junto. Posiciona com ``after`` sem ligar a original
    como pré-requisito (``link_after=False``).
    """
    copy_label = f"Copy of {activity.label}"[:300]
    return add_activity(
        activity.release,
        label=copy_label,
        step=activity.step,
        description=activity.description,
        objectives=_strip_marks(activity.objectives),
        after=activity,
        depends_on_ids=[],
        mode=activity.mode,
        github_repo=activity.github_repo,
        area=activity.area,
        size=activity.size,
        resources=list(activity.resources or []),
        assignee=activity.assignee,
        link_after=False,
    )


@transaction.atomic
def move_activity(activity: Activity, *, step: ReleaseStep, after: Activity | None = None) -> Activity:
    _assert_mutable(activity.release)
    if step.release_id != activity.release.id:
        raise WorkflowError("That step isn't in this release.")
    if after is not None and after.release_id != activity.release.id:
        raise WorkflowError("That activity isn't in this release.")
    if after is not None and after.id == activity.id:
        raise WorkflowError("An activity can't be moved after itself.")

    old_order = activity.order
    old_step = activity.step
    new_order = (after.order + 1) if after else 0

    Activity.objects.filter(release=activity.release, step=old_step, order__gt=old_order).update(order=F("order") - 1)
    Activity.objects.filter(release=activity.release, step=step, order__gte=new_order).exclude(id=activity.id).update(
        order=F("order") + 1
    )

    activity.step = step
    activity.order = new_order
    activity.save(update_fields=["step", "order", "updated_at"])
    # o título do ticket contém o label do step — re-sincroniza após mover
    _sync_later(activity)
    return activity


def ensure_no_dependency_cycle(nodes, node_id: int, new_dep_ids: list[int]) -> None:
    """Raise WorkflowError if replacing node's deps with new_dep_ids would create a cycle."""
    edges = {n.id: set(n.depends_on.values_list("id", flat=True)) for n in nodes}
    edges[node_id] = set(new_dep_ids)
    if node_id in edges[node_id]:
        raise WorkflowError("An activity can't depend on itself.")
    stack, seen = list(edges[node_id]), set(edges[node_id])
    while stack:
        cur = stack.pop()
        if cur == node_id:
            raise WorkflowError("That dependency would create a loop.")
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)


@transaction.atomic
def delete_activity(activity: Activity) -> None:
    _assert_mutable(activity.release)
    # em draft qualquer status é removível (blocked nasce de deps pendentes e
    # nada começou); em execução só atividades que ainda não começaram (todo)
    if activity.release.status != DataRelease.Status.DRAFT and activity.status != Activity.Status.TODO:
        raise WorkflowError("In a started release, you can delete only To do activities.")
    if activity.dependents.exists():
        raise WorkflowError("Other activities depend on this one. Remove those dependencies first.")
    # integrações: fecha a issue/ticket órfãos depois do commit (best-effort)
    _cleanup_after_delete_later(
        release_status=activity.release.status,
        github_repo=activity.github_repo,
        github_issue_number=activity.github_issue_number,
        glpi_ticket_id=activity.glpi_ticket_id,
        label=activity.label,
    )
    activity.delete()


def _cleanup_after_delete_later(*, release_status, github_repo, github_issue_number, glpi_ticket_id, label) -> None:
    """Agenda o fechamento de issue/ticket de uma atividade removida (on_commit)."""
    from idac_drd.integrations.sync import cleanup_deleted_activity

    _after_commit(cleanup_deleted_activity, release_status, github_repo, github_issue_number, glpi_ticket_id, label)


def archive_release(release: DataRelease) -> DataRelease:
    release.status = DataRelease.Status.ARCHIVED
    release.archived_at = timezone.now()
    release.save(update_fields=["status", "archived_at", "updated_at"])
    return release


def unarchive_release(release: DataRelease) -> DataRelease:
    # Sem execução iniciada, desarquivar volta para draft; senão retoma a execução.
    any_started = release.activities.filter(started_at__isnull=False).exists()
    release.status = DataRelease.Status.ACTIVE if any_started else DataRelease.Status.DRAFT
    release.archived_at = None
    release.save(update_fields=["status", "archived_at", "updated_at"])
    return release


@transaction.atomic
def start_release(release: DataRelease) -> DataRelease:
    """Gesto formal de início de execução: marcar started_at; o draft segue editável."""
    if release.status != DataRelease.Status.DRAFT:
        raise WorkflowError("You can start only draft releases.")
    if not release.activities.exists():
        raise WorkflowError("Add an activity before starting the release.")
    release.status = DataRelease.Status.ACTIVE
    release.started_at = timezone.now()
    release.save(update_fields=["status", "started_at", "updated_at"])
    # âncoras das threads antes dos replies (on_commit roda em ordem FIFO)
    _notify_started_later(release)
    # ao iniciar a execução, todo activity vira issue/ticket nas integrações
    for activity in release.activities.all():
        _sync_later(activity)
        if activity.status == Activity.Status.TODO:
            _mark_ready(activity)
            if activity.assignee_id:
                _notify_ready_later(activity)
    return release


@transaction.atomic
def add_step_to_release(
    release: DataRelease,
    *,
    label: str,
    key: str | None = None,
    color: str = "#000099",
    order: int | None = None,
    resources: list | None = None,
) -> ReleaseStep:
    _assert_mutable(release)
    _resume_completed_release(release)
    step_key = key or slugify(label)
    if ReleaseStep.objects.filter(release=release, key=step_key).exists():
        raise WorkflowError(f"This release already has a step with the key '{step_key}'.")
    if order is None:
        last = release.steps.aggregate(m=Max("order"))["m"]
        order = 0 if last is None else last + 1
    return ReleaseStep.objects.create(
        release=release,
        key=step_key,
        label=label,
        order=order,
        color=color,
        resources=resources or [],
    )


def update_release_step(
    step: ReleaseStep,
    *,
    label: str | None = None,
    color: str | None = None,
    order: int | None = None,
    resources: list | None = None,
) -> ReleaseStep:
    _assert_mutable(step.release)
    if label is not None:
        step.label = label
    if color is not None:
        step.color = color
    if order is not None:
        step.order = order
    if resources is not None:
        step.resources = resources
    step.save()
    # o título do ticket contém o label do step — re-sincroniza as atividades
    for activity in step.activities.all():
        _sync_later(activity)
    return step


def delete_release_step(step: ReleaseStep) -> None:
    _assert_mutable(step.release)
    if step.activities.exists():
        raise WorkflowError("You can delete a step only if it has no activities.")
    release = step.release
    step.delete()
    _renormalize_step_orders(release)


def _renormalize_step_orders(release: DataRelease, steps: list[ReleaseStep] | None = None) -> None:
    """Garante order 0..n-1 únicos, na ordem visual (order, id)."""
    steps = steps if steps is not None else list(release.steps.order_by("order", "id"))
    for i, item in enumerate(steps):
        if item.order != i:
            item.order = i
            item.save(update_fields=["order"])


@transaction.atomic
def reorder_release_step(step: ReleaseStep, direction: int) -> ReleaseStep:
    """Troca o step com o vizinho na ordem visual e compacta os orders."""
    _assert_mutable(step.release)
    if direction not in (-1, 1):
        raise WorkflowError("Direction must be -1 or 1.")
    steps = list(step.release.steps.order_by("order", "id"))
    idx = next(i for i, item in enumerate(steps) if item.id == step.id)
    swap_idx = idx + direction
    if swap_idx < 0 or swap_idx >= len(steps):
        return step
    steps[idx], steps[swap_idx] = steps[swap_idx], steps[idx]
    _renormalize_step_orders(step.release, steps)
    step.refresh_from_db()
    return step


def export_draft_payload(release: DataRelease) -> dict:
    """Serializa a estrutura de uma release no formato de arquivo de draft (v1).

    Fonte canônica do shape consumido por ``import_draft_payload``: activities
    referenciam steps por key, dependências por keys e assignee por email —
    nenhum id sobrevive ao arquivo. Funciona para qualquer status (exportar uma
    release executada permite criar o próximo draft a partir dela).
    """
    steps = [
        {
            "key": step.key,
            "label": step.label,
            "order": step.order,
            "color": step.color,
            "resources": step.resources,
        }
        for step in release.steps.all()
    ]
    activities = []
    for activity in release.activities.select_related("step", "assignee").all():
        activities.append(
            {
                "key": activity.key,
                "label": activity.label,
                "step_key": activity.step.key,
                "description": activity.description,
                "objectives": activity.objectives,
                "order": activity.order,
                "mode": activity.mode,
                "github_repo": activity.github_repo,
                "area": activity.area,
                "size": activity.size,
                "resources": activity.resources,
                "assignee_email": activity.assignee.email if activity.assignee else None,
                "depends_on": list(activity.depends_on.order_by("order", "id").values_list("key", flat=True)),
            }
        )
    return {
        "format": "idac_drd-draft",
        "version": 1,
        "name": release.name,
        "steps": steps,
        "activities": activities,
    }


@transaction.atomic
def import_draft_payload(data: dict) -> DataRelease:
    """Cria um draft a partir do formato de arquivo de draft (v1).

    Espelha ``_clone_structure`` com fonte JSON: steps primeiro (mapa por key),
    activities depois (assignee por email, status sempre reseta para todo) e
    dependências resolvidas por key num segundo passe. Sem sync de integrações:
    a release nasce draft e a sync só roda com a release em execução.
    """
    release = DataRelease.objects.create(
        name=data["name"],
        slug=slugify(data["name"]),
        status=DataRelease.Status.DRAFT,
        template_key="",
    )

    step_map: dict[str, ReleaseStep] = {}
    for step_data in data["steps"]:
        step_map[step_data["key"]] = ReleaseStep.objects.create(
            release=release,
            key=step_data["key"],
            label=step_data["label"],
            order=step_data.get("order", 0),
            color=step_data.get("color", "#000099"),
            resources=step_data.get("resources", []),
        )

    emails = {a["assignee_email"] for a in data["activities"] if a.get("assignee_email")}
    identity_by_email = {
        identity.email.lower(): identity for identity in ExternalIdentity.objects.filter(email__in=emails)
    }

    activity_map: dict[str, Activity] = {}
    for act_data in data["activities"]:
        assignee_email = act_data.get("assignee_email")
        activity_map[act_data["key"]] = Activity.objects.create(
            release=release,
            step=step_map[act_data["step_key"]],
            key=act_data["key"],
            label=act_data["label"],
            description=act_data.get("description", ""),
            objectives=act_data.get("objectives", ""),
            order=act_data.get("order", 0),
            status=Activity.Status.TODO,
            mode=act_data.get("mode", Activity.Mode.MANUAL),
            github_repo=act_data.get("github_repo", ""),
            area=act_data.get("area", ""),
            size=act_data.get("size", ""),
            resources=act_data.get("resources", []),
            assignee=identity_by_email.get(assignee_email.lower()) if assignee_email else None,
        )

    for act_data in data["activities"]:
        dep_keys = act_data.get("depends_on") or []
        if dep_keys:
            activity_map[act_data["key"]].depends_on.set({activity_map[k].id for k in dep_keys if k in activity_map})
        _block_until_prerequisites(activity_map[act_data["key"]])

    return release
