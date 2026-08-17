import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

from idac_drd.workflow.models import Activity, ActivityTransition, DataRelease, ReleaseStep

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


def _safe(call, *args):
    """Chama o callback de integração sem deixar exceção escapar do on_commit.

    O commit já aconteceu quando o callback roda — uma exceção aqui viraria um
    500 pós-commit e o usuário repetiria a ação. Erro vira log, nada mais.
    """
    try:
        call(*args)
    except Exception:  # noqa: BLE001 — pós-commit, erro só loga
        logger.exception("Integration callback %s failed", getattr(call, "__name__", call))


def _sync_later(activity: Activity) -> None:
    """Agenda a sync de integrações (GitHub/GLPI) para depois do commit.

    As chamadas HTTP nunca rodam dentro de uma transação aberta. A própria sync
    decide se aplica (gate: release em execução + flags *_ENABLED).
    """
    from idac_drd.integrations.sync import sync_activity

    transaction.on_commit(lambda: _safe(sync_activity, activity))


def _notify_review_later(activity: Activity) -> None:
    """Agenda o aviso de review (Slack DM ao aprovador) para depois do commit.

    O callback roda fora da transação; a notificação decide se aplica
    (gate: release em execução + SLACK_ENABLED) e nunca levanta.
    """
    from idac_drd.integrations.notify import notify_review

    transaction.on_commit(lambda: _safe(notify_review, activity))


def _notify_rejection_later(activity: Activity, comment: str, reviewer=None) -> None:
    """Agenda o aviso de rejeição (Slack DM ao executor) para depois do commit."""
    from idac_drd.integrations.notify import notify_rejection

    reviewer_name = reviewer.username if reviewer else ""
    transaction.on_commit(lambda: _safe(notify_rejection, activity, comment, reviewer_name))


def _clone_structure(source_steps, source_items, target: DataRelease) -> DataRelease:
    """Copia steps + activities de uma release de origem para a release-alvo.

    Itens precisam expor step, key, label, description, objectives, order,
    mode, github_repo, area, size, assignee e depends_on. Status sempre reseta
    para todo.
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
            objectives=item.objectives,
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
        # releases clonadas já em execução criam issues/tickets para cada activity
        _sync_later(activity)
    return target


@transaction.atomic
def create_plan(
    *,
    name: str,
    slug: str | None = None,
    copy_from_release: DataRelease | None = None,
) -> DataRelease:
    """Cria um plano (draft) em branco ou copiando uma release anterior.

    O plano é o objeto primário: nasce ``planned`` sem ``started_at`` e só
    sai do rascunho via ``start_release``. ``template_key`` guarda a origem
    histórica (string) quando a release copiada veio de um template.
    """
    release = DataRelease.objects.create(
        name=name,
        slug=slug or slugify(name),
        status=DataRelease.Status.PLANNED,
        template_key=(copy_from_release.template_key if copy_from_release else ""),
    )
    if copy_from_release is not None:
        _clone_structure(copy_from_release.steps.all(), copy_from_release.activities.all(), release)
    return release


def _approver_allowed(activity: Activity, actor) -> bool:
    """Quem pode aprovar (→ done) uma atividade em revisão.

    Aprovador natural: assignee da próxima activity do mesmo step (match por
    email); sem próxima activity, só staff; próxima sem assignee, qualquer pessoa.
    Chamadas de sistema (actor=None) passam — e staff sempre pode aprovar
    (dono do processo; evita beco sem saída com assignees sem conta no app).
    """
    if actor is None:
        return True
    if getattr(actor, "is_staff", False):
        return True
    next_activity = activity.next_in_step()
    if next_activity is None:
        return False
    if next_activity.assignee is None:
        return True
    email = (getattr(actor, "email", "") or "").lower()
    return bool(email) and email == (next_activity.assignee.email or "").lower()


def _assert_mutable(release: DataRelease) -> None:
    if release.is_readonly:
        raise WorkflowError("Archived releases are read-only.")


def transition_activity(
    activity: Activity,
    *,
    to_status: str,
    actor=None,
    comment: str = "",
) -> Activity:
    _assert_mutable(activity.release)
    if activity.release.status == DataRelease.Status.PLANNED:
        raise WorkflowError("Execution only starts after the plan is started.")
    if to_status not in Activity.Status.values:
        raise WorkflowError(f"Invalid status: {to_status}")

    if (
        to_status in (Activity.Status.IN_PROGRESS, Activity.Status.IN_REVIEW, Activity.Status.DONE)
        and not activity.prerequisites_met()
    ):
        pending = list(activity.depends_on.exclude(status=Activity.Status.DONE).values_list("label", flat=True))
        raise WorkflowError(
            "Prerequisites not completed: " + ", ".join(pending) if pending else "Prerequisites not completed."
        )

    if to_status == Activity.Status.BLOCKED and not (activity.blocked_reason or comment):
        raise WorkflowError("blocked_reason is required when blocking an activity.")

    from_status = activity.status
    if from_status == to_status:
        return activity

    if to_status == Activity.Status.IN_REVIEW:
        if from_status not in (Activity.Status.IN_PROGRESS, Activity.Status.BLOCKED):
            raise WorkflowError("Only in-progress (or unblocked) activities can be sent to review.")
    elif to_status == Activity.Status.DONE:
        # done = aprovação: só de in_review e pelo aprovador certo
        if from_status != Activity.Status.IN_REVIEW:
            raise WorkflowError("Only in-review activities can be approved.")
        if not _approver_allowed(activity, actor):
            raise WorkflowError("Only the assignee of the next activity (or staff) can approve this activity.")
    elif to_status == Activity.Status.IN_PROGRESS and from_status == Activity.Status.IN_REVIEW:
        # rejeição da revisão: exige motivo
        if not comment:
            raise WorkflowError("A reason is required when rejecting a review.")

    now = timezone.now()
    activity.status = to_status
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
    sync_release_completion(activity.release)
    _sync_later(activity)
    if to_status == Activity.Status.IN_REVIEW:
        _notify_review_later(activity)
    elif to_status == Activity.Status.IN_PROGRESS and from_status == Activity.Status.IN_REVIEW:
        # rejeição da revisão: avisa o executor para corrigir
        _notify_rejection_later(activity, comment, actor)
    return activity


def sync_release_completion(release: DataRelease) -> bool:
    """Marca a release como completed quando todas as atividades estão done;
    volta para active se alguma atividade deixou de estar done (releases
    arquivadas não são tocadas)."""
    all_done = not release.activities.exclude(status=Activity.Status.DONE).exists()
    target = DataRelease.Status.COMPLETED if all_done else DataRelease.Status.ACTIVE
    if release.status == DataRelease.Status.PLANNED or release.status == DataRelease.Status.ARCHIVED:
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
) -> Activity:
    _assert_mutable(release)
    if step.release_id != release.id:
        raise WorkflowError("Step does not belong to this release.")

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
    )

    deps = []
    if after:
        deps.append(after)
    if depends_on_ids:
        deps.extend(list(Activity.objects.filter(release=release, id__in=depends_on_ids)))
    if deps:
        activity.depends_on.set({d.id for d in deps})
    _sync_later(activity)
    return activity


@transaction.atomic
def move_activity(activity: Activity, *, step: ReleaseStep, after: Activity | None = None) -> Activity:
    _assert_mutable(activity.release)
    if step.release_id != activity.release.id:
        raise WorkflowError("Step does not belong to this release.")
    if after is not None and after.release_id != activity.release.id:
        raise WorkflowError("After activity does not belong to this release.")
    if after is not None and after.id == activity.id:
        raise WorkflowError("Cannot move an activity after itself.")

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
    return activity


def ensure_no_dependency_cycle(nodes, node_id: int, new_dep_ids: list[int]) -> None:
    """Raise WorkflowError if replacing node's deps with new_dep_ids would create a cycle."""
    edges = {n.id: set(n.depends_on.values_list("id", flat=True)) for n in nodes}
    edges[node_id] = set(new_dep_ids)
    if node_id in edges[node_id]:
        raise WorkflowError("An activity cannot depend on itself.")
    stack, seen = list(edges[node_id]), set(edges[node_id])
    while stack:
        cur = stack.pop()
        if cur == node_id:
            raise WorkflowError("Dependencies would create a cycle.")
        for nxt in edges.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)


@transaction.atomic
def delete_activity(activity: Activity) -> None:
    _assert_mutable(activity.release)
    if activity.status != Activity.Status.TODO:
        raise WorkflowError("Only todo activities can be deleted.")
    if activity.dependents.exists():
        raise WorkflowError("Activity has dependents; remove or rewire them first.")
    activity.delete()


def archive_release(release: DataRelease) -> DataRelease:
    release.status = DataRelease.Status.ARCHIVED
    release.archived_at = timezone.now()
    release.save(update_fields=["status", "archived_at", "updated_at"])
    return release


def unarchive_release(release: DataRelease) -> DataRelease:
    # Sem execução iniciada, desarquivar volta para draft; senão retoma a execução.
    any_started = release.activities.filter(started_at__isnull=False).exists()
    release.status = DataRelease.Status.ACTIVE if any_started else DataRelease.Status.PLANNED
    release.archived_at = None
    release.save(update_fields=["status", "archived_at", "updated_at"])
    return release


@transaction.atomic
def start_release(release: DataRelease) -> DataRelease:
    """Gesto formal de início de execução: marcar started_at; o plano segue editável."""
    if release.status != DataRelease.Status.PLANNED:
        raise WorkflowError("Only planned releases can be started.")
    if not release.activities.exists():
        raise WorkflowError("Add at least one activity before starting the release.")
    release.status = DataRelease.Status.ACTIVE
    release.started_at = timezone.now()
    release.save(update_fields=["status", "started_at", "updated_at"])
    # ao iniciar a execução, todo activity vira issue/ticket nas integrações
    for activity in release.activities.all():
        _sync_later(activity)
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
    step_key = key or slugify(label)
    if ReleaseStep.objects.filter(release=release, key=step_key).exists():
        raise WorkflowError(f"Step key '{step_key}' already exists in this release.")
    return ReleaseStep.objects.create(
        release=release,
        key=step_key,
        label=label,
        order=order if order is not None else release.steps.count(),
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
    return step


def delete_release_step(step: ReleaseStep) -> None:
    _assert_mutable(step.release)
    if step.activities.exists():
        raise WorkflowError("Only empty steps can be deleted.")
    step.delete()
