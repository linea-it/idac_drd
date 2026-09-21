"""Helpers de fixtures: releases construídas pelos serviços reais.

Substitui o padrão antigo de carregar templates (load_template_from_dict)
para montar estruturas de teste — hoje os templates não existem mais e o
caminho canônico é ``create_draft`` + ``add_step_to_release`` + ``add_activity``.
"""

from datetime import timedelta

from django.utils import timezone

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, ActivityWorkSession, DataRelease
from idac_drd.workflow.services import add_activity, add_step_to_release, create_draft, start_release

#: estrutura de referência: 2 steps, cada um com 1 activity
DEFAULT_STEPS = [
    {"key": "a", "label": "Step A", "color": "#000099"},
    {"key": "b", "label": "Step B"},
]
DEFAULT_ACTIVITIES = [
    {"key": "step-1", "label": "Step 1", "step": "a", "depends_on": []},
    {"key": "step-2", "label": "Step 2", "step": "a", "depends_on": ["step-1"]},
]


def prime_effort(activity, actor=None):
    """Garante ≥1 sessão fechada — gate de in_review (Play é a porta real em produção)."""
    assignee = activity.assignee
    if assignee is None:
        assignee, _ = ExternalIdentity.objects.get_or_create(
            email=f"effort-act-{activity.pk}@test.local",
            defaults={"name": "Effort Fixture"},
        )
        Activity.objects.filter(pk=activity.pk).update(assignee=assignee)
        activity.assignee_id = assignee.id
    if activity.work_sessions.exists():
        return activity
    now = timezone.now()
    ActivityWorkSession.objects.create(
        activity=activity,
        assignee=assignee,
        started_at=now - timedelta(seconds=5),
        ended_at=now,
        end_reason=ActivityWorkSession.EndReason.PAUSE,
        actor=actor if getattr(actor, "pk", None) else None,
    )
    return activity


def make_release(name, *, slug=None, status="active", steps=DEFAULT_STEPS, activities=DEFAULT_ACTIVITIES):
    """Cria release completa pelos serviços reais.

    ``steps``/``activities`` usam os mesmos dicts da antiga fixture de template.
    ``status``: "draft" deixa em rascunho; "active" inicia a execução.
    """
    release = create_draft(name=name, slug=slug)
    step_map = {}
    for step in steps:
        kwargs = {"label": step["label"], "key": step["key"]}
        if step.get("color"):
            kwargs["color"] = step["color"]
        step_map[step["key"]] = add_step_to_release(release, **kwargs)
    activity_key_map = {}
    for act in activities:
        dep_ids = [activity_key_map[d].id for d in act.get("depends_on", []) if d in activity_key_map]
        kwargs = {
            "label": act["label"],
            "key": act["key"],
            "step": step_map[act["step"]],
            "depends_on_ids": dep_ids,
            "mode": act.get("mode", "manual"),
        }
        for field in ("description", "objectives", "github_repo", "area", "size"):
            if act.get(field):
                kwargs[field] = act[field]
        new_act = add_activity(release, **kwargs)
        activity_key_map[act["key"]] = new_act
    if status == "active":
        start_release(release)
    elif status != "draft":
        release.status = DataRelease.Status(status)
        release.save(update_fields=["status"])
    return release
