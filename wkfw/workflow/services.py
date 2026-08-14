from __future__ import annotations

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

from wkfw.workflow.models import (
    Activity,
    ActivityTransition,
    DataRelease,
    ReleaseLane,
    TemplateLane,
    TemplateStage,
    WorkflowTemplate,
)


class WorkflowError(Exception):
    pass


def clone_template_to_release(template: WorkflowTemplate, release: DataRelease) -> DataRelease:
    lane_map: dict[str, ReleaseLane] = {}
    for lane in template.lanes.all():
        lane_map[lane.key] = ReleaseLane.objects.create(
            release=release,
            key=lane.key,
            label=lane.label,
            order=lane.order,
            color=lane.color,
        )

    stage_to_activity: dict[int, Activity] = {}
    for stage in template.stages.select_related("lane").all():
        activity = Activity.objects.create(
            release=release,
            lane=lane_map[stage.lane.key],
            key=stage.key,
            label=stage.label,
            description=stage.description,
            order=stage.order,
            status=Activity.Status.TODO,
        )
        stage_to_activity[stage.id] = activity

    for stage in template.stages.prefetch_related("depends_on").all():
        activity = stage_to_activity[stage.id]
        dep_ids = [stage_to_activity[dep.id].id for dep in stage.depends_on.all() if dep.id in stage_to_activity]
        if dep_ids:
            activity.depends_on.set(dep_ids)

    release.template = template
    if not release.started_at and release.status == DataRelease.Status.ACTIVE:
        release.started_at = timezone.now()
    release.save()
    return release


@transaction.atomic
def create_release_from_template(
    *,
    name: str,
    template: WorkflowTemplate,
    slug: str | None = None,
    status: str = DataRelease.Status.ACTIVE,
) -> DataRelease:
    release = DataRelease.objects.create(
        name=name,
        slug=slug or slugify(name),
        status=status,
        template=template,
        started_at=timezone.now() if status == DataRelease.Status.ACTIVE else None,
    )
    return clone_template_to_release(template, release)


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
    if to_status not in Activity.Status.values:
        raise WorkflowError(f"Invalid status: {to_status}")

    if to_status in (Activity.Status.IN_PROGRESS, Activity.Status.DONE) and not activity.prerequisites_met():
        pending = list(activity.depends_on.exclude(status=Activity.Status.DONE).values_list("label", flat=True))
        raise WorkflowError(
            "Prerequisites not completed: " + ", ".join(pending) if pending else "Prerequisites not completed."
        )

    if to_status == Activity.Status.BLOCKED and not (activity.blocked_reason or comment):
        raise WorkflowError("blocked_reason is required when blocking an activity.")

    from_status = activity.status
    if from_status == to_status:
        return activity

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
    return activity


def sync_release_completion(release: DataRelease) -> bool:
    """Marca a release como completed quando todas as atividades estão done;
    volta para active se alguma atividade deixou de estar done (releases
    arquivadas não são tocadas)."""
    all_done = not release.activities.exclude(status=Activity.Status.DONE).exists()
    target = DataRelease.Status.COMPLETED if all_done else DataRelease.Status.ACTIVE
    if release.status == DataRelease.Status.ARCHIVED or release.status == target:
        return False
    release.status = target
    release.save(update_fields=["status", "updated_at"])
    return True


@transaction.atomic
def add_activity(
    release: DataRelease,
    *,
    label: str,
    lane: ReleaseLane,
    key: str | None = None,
    description: str = "",
    after: Activity | None = None,
    depends_on_ids: list[int] | None = None,
    mode: str = Activity.Mode.MANUAL,
) -> Activity:
    _assert_mutable(release)
    if lane.release_id != release.id:
        raise WorkflowError("Lane does not belong to this release.")

    activity_key = key or slugify(label)
    if Activity.objects.filter(release=release, key=activity_key).exists():
        activity_key = f"{activity_key}-{Activity.objects.filter(release=release).count() + 1}"

    if after:
        order = after.order + 1
    elif lane.activities.exists():
        order = lane.activities.order_by("-order").first().order + 1
    else:
        order = 0

    Activity.objects.filter(release=release, lane=lane, order__gte=order).update(order=F("order") + 1)

    activity = Activity.objects.create(
        release=release,
        lane=lane,
        key=activity_key,
        label=label,
        description=description,
        order=order,
        status=Activity.Status.TODO,
        mode=mode,
    )

    deps = []
    if after:
        deps.append(after)
    if depends_on_ids:
        deps.extend(list(Activity.objects.filter(release=release, id__in=depends_on_ids)))
    if deps:
        activity.depends_on.set({d.id for d in deps})
    return activity


@transaction.atomic
def move_activity(activity: Activity, *, lane: ReleaseLane, after: Activity | None = None) -> Activity:
    _assert_mutable(activity.release)
    if lane.release_id != activity.release.id:
        raise WorkflowError("Lane does not belong to this release.")
    if after is not None and after.release_id != activity.release.id:
        raise WorkflowError("After activity does not belong to this release.")
    if after is not None and after.id == activity.id:
        raise WorkflowError("Cannot move an activity after itself.")

    old_order = activity.order
    old_lane = activity.lane
    new_order = (after.order + 1) if after else 0

    Activity.objects.filter(release=activity.release, lane=old_lane, order__gt=old_order).update(
        order=F("order") - 1
    )
    Activity.objects.filter(release=activity.release, lane=lane, order__gte=new_order).exclude(
        id=activity.id
    ).update(order=F("order") + 1)

    activity.lane = lane
    activity.order = new_order
    activity.save(update_fields=["lane", "order", "updated_at"])
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
    release.status = DataRelease.Status.ACTIVE
    release.archived_at = None
    release.save(update_fields=["status", "archived_at", "updated_at"])
    return release


@transaction.atomic
def load_template_from_dict(data: dict) -> WorkflowTemplate:
    template, _ = WorkflowTemplate.objects.update_or_create(
        key=data["key"],
        defaults={
            "name": data["name"],
            "version": data.get("version", 1),
            "is_active": data.get("is_active", True),
        },
    )
    template.stages.all().delete()
    template.lanes.all().delete()

    lane_map: dict[str, TemplateLane] = {}
    for lane_data in data.get("lanes", []):
        lane_map[lane_data["key"]] = TemplateLane.objects.create(
            template=template,
            key=lane_data["key"],
            label=lane_data["label"],
            order=lane_data.get("order", 0),
            color=lane_data.get("color", "#000099"),
        )

    stage_map: dict[str, TemplateStage] = {}
    for stage_data in data.get("stages", []):
        stage_map[stage_data["key"]] = TemplateStage.objects.create(
            template=template,
            lane=lane_map[stage_data["lane"]],
            key=stage_data["key"],
            label=stage_data["label"],
            description=stage_data.get("description", ""),
            order=stage_data.get("order", 0),
        )

    for stage_data in data.get("stages", []):
        deps = [stage_map[k] for k in stage_data.get("depends_on", []) if k in stage_map]
        if deps:
            stage_map[stage_data["key"]].depends_on.set(deps)

    return template
