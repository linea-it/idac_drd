"""Sync automática de atividades ↔ GitHub/GLPI (integrations/sync.py).

Best-effort + gates: release em execução e flags *_ENABLED. Clients reais
são substituídos por fakes — nada de HTTP.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from idac_drd.integrations import sync

User = get_user_model()
from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, ActivityTransition, DataRelease, ReleaseStep

ENABLED = {
    "GH_ENABLED": True,
    "GLPI_ENABLED": True,
}


PROJECT_FIELD = (
    "PVT_proj",
    "f_status",
    {
        "🔖 To do": "o_todo",
        "🏗 In progress": "o_in_progress",
        "🚧 Blocked": "o_blocked",
        "👀 In review": "o_in_review",
        "✅ Done": "o_done",
    },
)


class FakeGithub:
    def __init__(self):
        self.created = []
        self.bodies = []
        self.updated = []
        self.project_field_calls = 0
        self.added_items = []
        self.set_statuses = []

    def create_issue(self, owner, repo, title, body, labels=None):
        self.created.append((owner, repo, title))
        self.bodies.append(body)
        return {"number": 42, "node_id": "I_kw_node42"}

    def update_issue(self, owner, repo, number, **fields):
        self.updated.append((owner, repo, number, fields))
        return {"number": number}

    def project_field(self, org, project_number):
        self.project_field_calls += 1
        return PROJECT_FIELD

    def add_project_item(self, project_id, content_id):
        self.added_items.append((project_id, content_id))
        return "PVTI_item42"

    def set_project_item_status(self, project_id, item_id, field_id, option_id):
        self.set_statuses.append((project_id, item_id, field_id, option_id))


class FakeGlpi:
    """Estado mínimo do ticket 7: status, name/content, assignees e followups."""

    def __init__(self, normalize=False):
        self.normalize = normalize  # simula o GLPI devolvendo o HTML normalizado
        self.created = []
        self.contents = []
        self.updated = []
        self.followups = []
        self.events = []  # ordem das chamadas (update/followup) — bug do fechamento
        self.status = 1
        self.name = None
        self.content = None
        self.pending_reason = None
        self.assignees = []  # users_ids dos atores type 2
        self.ticket_users = []  # entradas {"id", "users_id", "type"}

    def create_ticket(self, name, content, ticket_type=1):
        self.created.append((name, ticket_type))
        self.contents.append(content)
        self.name = name
        self.content = content
        return {"id": 7}

    def update_ticket(self, ticket_id, **fields):
        self.updated.append((ticket_id, fields))
        self.events.append(("update", fields))
        if "status" in fields:
            self.status = fields["status"]
        if "name" in fields:
            self.name = fields["name"]
        if "content" in fields:
            self.content = fields["content"]
        if "pending_reason" in fields:
            self.pending_reason = fields["pending_reason"]
        return {"id": ticket_id}

    def get_ticket(self, ticket_id):
        content = self.content.replace("\n", "<br>") if self.normalize else self.content
        return {
            "id": ticket_id,
            "status": self.status,
            "name": self.name,
            "content": content,
            "pending_reason": self.pending_reason,
        }

    def get_ticket_users(self, ticket_id):
        return list(self.ticket_users)

    def assign_ticket(self, ticket_id, users_id):
        self.assignees.append(users_id)
        self.ticket_users.append({"id": len(self.ticket_users) + 1, "users_id": users_id, "type": 2})
        self.status = 2  # promoção automática do GLPI ao atribuir executor
        return {"id": ticket_id}

    def unassign_ticket(self, ticket_id, ticket_user_id):
        self.ticket_users = [u for u in self.ticket_users if u["id"] != ticket_user_id]
        self.assignees = [u["users_id"] for u in self.ticket_users]
        return {"id": ticket_id}

    def add_followup(self, ticket_id, content):
        self.followups.append(content)
        self.events.append(("followup", content))
        return {"id": 1}


@pytest.fixture
def clients(monkeypatch):
    gh, glpi = FakeGithub(), FakeGlpi()
    monkeypatch.setattr("idac_drd.integrations.sync._github_client", lambda: gh)
    monkeypatch.setattr("idac_drd.integrations.sync._glpi_client", lambda: glpi)
    return gh, glpi


@pytest.fixture(autouse=True)
def reset_project_cache():
    # o cache do field Status do projeto é global; zera entre testes
    sync._PROJECT_CACHE.update({"ts": 0.0, "data": None})


@pytest.fixture
def release(db):
    release = DataRelease.objects.create(name="Release 1", slug="r1", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    return release


def make_activity(release, **overrides):
    values = {
        "release": release,
        "step": release.steps.get(),
        "key": "step-1",
        "label": "Step 1",
        "order": 0,
        "status": Activity.Status.TODO,
        "github_repo": "linea-it/repo",
    }
    values.update(overrides)
    return Activity.objects.create(**values)


def test_gated_by_release_status(clients, release):
    """Release fora de execução (draft/arquivada): no-op silencioso."""
    gh, glpi = clients
    release.status = DataRelease.Status.PLANNED
    release.save()
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))
    assert not gh.created and not gh.updated
    assert not glpi.created and not glpi.updated


def test_disabled_flags_noop(clients, release):
    """Flags *_ENABLED off: nada é criado nem atualizado."""
    gh, glpi = clients
    with override_settings(GH_ENABLED=False, GLPI_ENABLED=False):
        sync.sync_activity(make_activity(release))
    assert not gh.created and not gh.updated
    assert not glpi.created and not glpi.updated


def test_creates_issue_and_ticket(clients, release):
    """Atividade em todo (disponível) cria issue GitHub + ticket GLPI."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo
        sync.sync_activity(activity)

    assert gh.created == [("linea-it", "repo", "Step 1")]
    assert gh.added_items == [("PVT_proj", "I_kw_node42")]
    assert gh.set_statuses == [("PVT_proj", "PVTI_item42", "f_status", "o_todo")]
    assert glpi.created == [("Release 1 - Step A: Step 1", 1)]
    assert not glpi.updated  # ticket nasce new (1) — sem PUT na mesma passada
    # referências persistidas na atividade
    activity.refresh_from_db()
    assert activity.github_issue_number == 42
    assert activity.github_issue_node_id == "I_kw_node42"
    assert activity.github_project_item_id == "PVTI_item42"
    assert activity.glpi_ticket_id == 7


def test_no_ticket_for_blocked(clients, release):
    """Atividade bloqueada nunca gera ticket (não polui o helpdesk)."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.BLOCKED)
        sync.sync_activity(activity)
        activity.refresh_from_db()

    assert not glpi.created
    assert activity.glpi_ticket_id is None


def test_creates_once_then_updates_status(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria issue + ticket
        sync.sync_activity(activity)
        activity.refresh_from_db()
        sync.sync_activity(activity)  # refs existem → só atualiza (GH open)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity, from_status=Activity.Status.TODO, to_status=Activity.Status.IN_PROGRESS
        )
        activity.status = Activity.Status.IN_PROGRESS
        activity.save()
        sync.sync_activity(activity)  # execução: status do ticket → processing

    assert len(gh.created) == 1 and len(glpi.created) == 1
    assert len(gh.added_items) == 1  # item adicionado ao projeto uma única vez
    assert gh.project_field_calls == 1  # field do projeto cacheado (60s)
    assert gh.updated == [
        ("linea-it", "repo", 42, {"state": "open"}),
        ("linea-it", "repo", 42, {"state": "open"}),
    ]
    assert gh.set_statuses[-1] == ("PVT_proj", "PVTI_item42", "f_status", "o_in_progress")
    assert glpi.updated == [(7, {"status": 2})]


def test_done_closes_issue_and_closes_ticket(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria issue + ticket
        sync.sync_activity(activity)
        activity.refresh_from_db()

        activity.status = Activity.Status.DONE
        activity.save()
        sync.sync_activity(activity)

    assert gh.updated == [("linea-it", "repo", 42, {"state": "closed", "state_reason": "completed"})]
    # última atualização no projeto: ✅ Done
    assert gh.set_statuses[-1] == ("PVT_proj", "PVTI_item42", "f_status", "o_done")
    # aprovação fecha o ticket (closed = 6); sem solução automática
    assert glpi.updated == [(7, {"status": 6})]


def test_blocked_maps_to_pending(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria o ticket (new)
        sync.sync_activity(activity)
        activity.refresh_from_db()

        activity.status = Activity.Status.BLOCKED
        activity.save()
        sync.sync_activity(activity)

    assert gh.set_statuses[-1][3] == "o_blocked"
    assert glpi.updated == [(7, {"status": 4, "pending_reason": "Atividade bloqueada"})]


def test_without_github_repo_skips_issue_but_creates_ticket(clients, release, caplog):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release, github_repo="")  # todo
        sync.sync_activity(activity)

    assert not gh.created
    assert not gh.added_items and not gh.set_statuses
    assert glpi.created == [("Release 1 - Step A: Step 1", 1)]
    assert "no GitHub repo" in caplog.text


def test_project_unavailable_keeps_issue_and_ticket(clients, release, caplog):
    """Sem acesso ao projeto (scope/erro), o item é pulado — o resto continua."""
    gh, glpi = clients

    def boom(*args, **kwargs):
        raise RuntimeError("Resource not accessible by integration")

    gh.project_field = boom
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))  # todo

    assert gh.created == [("linea-it", "repo", "Step 1")]
    assert not gh.added_items
    assert glpi.created == [("Release 1 - Step A: Step 1", 1)]
    assert "GitHub project sync failed" in caplog.text


def test_in_review_maps_to_project_review_and_glpi_pending(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria o ticket (new)
        sync.sync_activity(activity)
        activity.refresh_from_db()

        activity.status = Activity.Status.IN_REVIEW
        activity.save()
        sync.sync_activity(activity)

    # issue segue aberta (fecha só na aprovação); projeto → In review; GLPI → Pending
    assert gh.updated == [("linea-it", "repo", 42, {"state": "open"})]
    assert gh.set_statuses[-1] == ("PVT_proj", "PVTI_item42", "f_status", "o_in_review")
    assert glpi.updated == [(7, {"status": 4, "pending_reason": 'Aguardando revisão da atividade "Step 1"'})]


def test_assigns_executor_on_in_progress(clients, release):
    gh, glpi = clients
    identity = ExternalIdentity.objects.create(email="executor@linea.org.br", name="Executor Silva", glpi_id=38)
    with override_settings(**ENABLED):
        activity = make_activity(release, assignee=identity)
        sync.sync_activity(activity)  # cria o ticket (new, sem ator)
        activity.refresh_from_db()
        # todo → in_progress (como no fluxo real, com ActivityTransition)
        ActivityTransition.objects.create(
            activity=activity, from_status=Activity.Status.TODO, to_status=Activity.Status.IN_PROGRESS
        )
        activity.status = Activity.Status.IN_PROGRESS
        activity.save()
        sync.sync_activity(activity)

    assert glpi.assignees == [38]
    assert glpi.status == 2  # promoção automática do GLPI
    assert glpi.followups == ['Atividade "Step 1" iniciada — executor: Executor Silva.']


def test_does_not_reassign_same_executor(clients, release):
    gh, glpi = clients
    identity = ExternalIdentity.objects.create(email="executor@linea.org.br", name="Executor Silva", glpi_id=38)
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS, assignee=identity)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        sync.sync_activity(activity)  # atribui
        sync.sync_activity(activity)  # idempotente: ator já atribuído, status já 2

    assert glpi.assignees == [38]
    assert len(glpi.followups) == 1  # nenhuma nota nem notificação em vão


def test_assignee_without_glpi_id_is_skipped(clients, release, caplog):
    gh, glpi = clients
    identity = ExternalIdentity.objects.create(email="executor@linea.org.br", name="Sem ID", glpi_id=None)
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS, assignee=identity)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        sync.sync_activity(activity)

    assert not glpi.assignees
    assert "has no glpi_id" in caplog.text


def test_closed_ticket_is_terminal(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        glpi.status = 6  # ticket já fechado no GLPI
        activity.status = Activity.Status.IN_PROGRESS
        activity.save()
        sync.sync_activity(activity)

    assert not glpi.updated and not glpi.followups  # nada mais é espelhado


def test_rejection_registers_comment_on_ticket(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_REVIEW,
            to_status=Activity.Status.IN_PROGRESS,
            comment="Corrigir o schema",
        )
        glpi.status = 4  # ticket estava pending na revisão
        activity.status = Activity.Status.IN_PROGRESS
        activity.save()
        sync.sync_activity(activity)

    assert glpi.updated == [(7, {"status": 2})]
    # recusa agora é HTML mínimo — o GLPI renderiza parágrafo e negrito
    assert glpi.followups == [
        "<p><strong>Revisão recusada</strong></p><p>Corrigir o schema. Voltou para execução.</p>"
    ]


def test_edit_resyncs_name_and_content(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria issue + ticket
        sync.sync_activity(activity)
        activity.refresh_from_db()
        # edição em execução: label e descrição mudam → ticket re-sincronizado
        activity.label = "Step 1 v2"
        activity.description = "Nova descrição"
        activity.save()
        sync.sync_activity(activity)

    # name composto (RELEASE - STEP: Activity) re-sincronizado junto; o status
    # não mudou, então não vai no PUT nem na nota
    assert glpi.updated == [(7, {"name": "Release 1 - Step A: Step 1 v2", "content": sync._ticket_body(activity)})]
    assert glpi.followups[-1] == (
        'Atividade "Step 1 v2" — título atualizado para "Release 1 - Step A: Step 1 v2", descrição atualizada.'
    )


def test_assignee_change_notes_author(clients, release):
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    identity = ExternalIdentity.objects.create(email="executor@linea.org.br", name="Executor Silva", glpi_id=38)
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)  # cria o ticket (execução) sem ator
        activity.refresh_from_db()
        # troca de executor por edição (sem transição) — sync leva o request.user
        activity.assignee = identity
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.assignees == [38]
    assert glpi.status == 2
    assert glpi.followups[-1] == ('Atividade "Step 1" — executor alterado para Executor Silva. (modificado por alice)')


def test_transition_note_includes_actor(clients, release):
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release)  # todo: cria o ticket
        sync.sync_activity(activity)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_PROGRESS,
            to_status=Activity.Status.BLOCKED,
            actor=user,
            comment="Esperando dados",
        )
        activity.status = Activity.Status.BLOCKED
        activity.save()
        sync.sync_activity(activity)

    assert glpi.followups[-1] == 'Atividade "Step 1" bloqueada: Esperando dados. (requisitado por alice)'


def test_objectives_go_to_issue_and_ticket_bodies(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(
            make_activity(
                release, objectives="Validar schema\nGerar dataset final", status=Activity.Status.IN_PROGRESS
            )
        )

    assert "**Objetivos:**" in gh.bodies[0]
    assert "- [ ] Validar schema" in gh.bodies[0]
    assert "- [ ] Gerar dataset final" in gh.bodies[0]
    assert "<p><strong>Objetivos:</strong></p>" in glpi.contents[0]
    assert "- [ ] Validar schema" in glpi.contents[0]


def test_objectives_preserve_checked_state(clients, release):
    """Objetivos marcados ([x] no campo) são espelhados; os demais seguem abertos."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(
            make_activity(
                release,
                objectives="[x] Validar schema\nGerar dataset final",
                status=Activity.Status.IN_PROGRESS,
            )
        )

    assert "- [x] Validar schema" in gh.bodies[0]
    assert "- [ ] Gerar dataset final" in gh.bodies[0]
    assert "- [x] Validar schema" in glpi.contents[0]
    assert "- [ ] Gerar dataset final" in glpi.contents[0]


def test_edit_notes_objectives_do_not_claim_status_change(clients, release):
    """Edição de notas/objetivos sem transição: a nota nomeia o que mudou, sem status."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        activity.objectives = "[ ] Criar schemas"
        activity.notes = "Falta o dataset de junho."
        activity.save()
        sync.sync_activity(activity, actor=user)

    # o status não mudou: a nota não o menciona, descreve só os campos alterados
    assert glpi.followups[-1] == (
        'Atividade "Step 1" — objetivos atualizados, notas atualizadas. (modificado por alice)'
    )


def test_edit_with_full_body_does_not_claim_description_change(clients, release):
    """Corpo com descrição+objetivos+notas: editar objetivos/notas não pode
    vazar o conteúdo das seções para a comparação de descrição."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(
            release,
            status=Activity.Status.IN_PROGRESS,
            description="Ingestão dos dados.",
            objectives="Criar schemas",
            notes="Base junho.",
        )
        sync.sync_activity(activity)
        activity.refresh_from_db()
        activity.objectives = "Criar schemas\nProcessar ingestao"
        activity.notes = "Falta o dataset de junho."
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.followups[-1] == (
        'Atividade "Step 1" — objetivos atualizados, notas atualizadas. (modificado por alice)'
    )
    # idempotência: a sync seguinte não vê mais nada a mudar
    glpi.events.clear()
    glpi.followups.clear()
    sync.sync_activity(activity)
    assert glpi.events == []


def test_edit_title_updates_ticket_name_and_note(clients, release):
    """Mudança de label re-sincroniza o título do ticket e a nota o registra."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        activity.label = "Step 1 v2"
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.updated[-1] == (7, {"name": "Release 1 - Step A: Step 1 v2"})
    assert glpi.followups[-1] == (
        'Atividade "Step 1 v2" — título atualizado para "Release 1 - Step A: Step 1 v2". (modificado por alice)'
    )


def test_notes_go_to_issue_and_ticket_bodies(clients, release):
    """Notas da atividade entram no corpo do ticket e da issue."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(
            make_activity(release, notes="Falta o dataset de junho.", status=Activity.Status.IN_PROGRESS)
        )

    assert "**Notas:**" in gh.bodies[0]
    assert "Falta o dataset de junho." in gh.bodies[0]
    assert "<p><strong>Notas:</strong></p>" in glpi.contents[0]
    assert "Falta o dataset de junho." in glpi.contents[0]


def test_ticket_body_escapes_html(clients, release):
    """Textos do dashboard entram crus em <p> — precisam de escape no corpo."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(
            make_activity(
                release,
                description="Comparar < 5 e & > 2",
                objectives="Testar <script>alert(1)</script>",
                notes="Nota com <b>negrito</b> & ampersand",
                status=Activity.Status.IN_PROGRESS,
            )
        )

    assert "Comparar &lt; 5 e &amp; &gt; 2" in glpi.contents[0]
    assert "&lt;script&gt;" in glpi.contents[0]
    assert "&lt;b&gt;negrito&lt;/b&gt; &amp; ampersand" in glpi.contents[0]


def test_rejection_reason_is_escaped(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_REVIEW,
            to_status=Activity.Status.IN_PROGRESS,
            comment="uso do <buffer> & cache",
        )
        glpi.status = 4  # ticket estava pending na revisão
        activity.status = Activity.Status.IN_PROGRESS
        activity.save()
        sync.sync_activity(activity)

    assert "&lt;buffer&gt; &amp; cache" in glpi.followups[-1]


def test_edit_removing_description_syncs_and_notes(clients, release):
    """Descrição apagada: o ticket perde a seção e a nota registra a mudança."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, description="Descrição antiga", status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        activity.description = ""
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.updated[-1] == (7, {"content": "<p>Sem descrição.</p>"})
    assert glpi.followups[-1] == ('Atividade "Step 1" — descrição atualizada. (modificado por alice)')


def test_edit_blocked_reason_syncs_pending_reason(clients, release):
    """Motivo do bloqueio editado (sem transição): pending_reason re-sincronizado."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_PROGRESS,
            to_status=Activity.Status.BLOCKED,
            actor=user,
            comment="Aguardando dados",
        )
        activity.status = Activity.Status.BLOCKED
        activity.blocked_reason = "Aguardando dados"
        activity.save()
        sync.sync_activity(activity)  # PUT status 4 + pending_reason
        glpi.followups.clear()
        glpi.events.clear()
        # edição do motivo sem mudança de status (sem transição nova)
        activity.blocked_reason = "Aguardando novo dataset"
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.updated[-1] == (7, {"pending_reason": "Aguardando novo dataset"})
    assert glpi.followups == ['Atividade "Step 1" — motivo do bloqueio atualizado. (modificado por alice)']


def test_unassign_removes_executor_on_ticket(clients, release):
    """Executor removido no dashboard: o ticket perde o assignee e ganha nota."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    identity = ExternalIdentity.objects.create(email="executor@linea.org.br", name="Executor Silva", glpi_id=38)
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS, assignee=identity)
        sync.sync_activity(activity)  # cria ticket + atribui
        activity.refresh_from_db()
        activity.assignee = None
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.assignees == []
    assert glpi.followups[-1] == 'Atividade "Step 1" — executor removido. (modificado por alice)'


def test_assignee_switch_removes_previous_executor(clients, release):
    """Trocar de executor: o antigo sai do ticket, o novo entra."""
    gh, glpi = clients
    first = ExternalIdentity.objects.create(email="a@linea.org.br", name="Executor A", glpi_id=38)
    second = ExternalIdentity.objects.create(email="b@linea.org.br", name="Executor B", glpi_id=41)
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS, assignee=first)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        activity.assignee = second
        activity.save()
        sync.sync_activity(activity)

    assert glpi.assignees == [41]
    assert glpi.followups[-1] == 'Atividade "Step 1" — executor alterado para Executor B.'


def test_approve_note_is_added_before_closing_put(clients, release):
    """Aprovação: a nota entra ANTES do PUT que fecha o ticket (followup em
    ticket fechado exige right específico no GLPI)."""
    gh, glpi = clients
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_PROGRESS,
            to_status=Activity.Status.IN_REVIEW,
            actor=user,
        )
        activity.status = Activity.Status.IN_REVIEW
        activity.save()
        sync.sync_activity(activity)
        glpi.events.clear()
        ActivityTransition.objects.create(
            activity=activity,
            from_status=Activity.Status.IN_REVIEW,
            to_status=Activity.Status.DONE,
            actor=user,
        )
        activity.status = Activity.Status.DONE
        activity.save()
        sync.sync_activity(activity)

    assert glpi.events == [
        ("followup", 'Atividade "Step 1" aprovada e concluída. (requisitado por alice)'),
        ("update", {"status": 6}),
    ]


def test_cleanup_deleted_activity_closes_issue_and_ticket(clients, release):
    """Atividade removida do plano: issue fechada e ticket encerrado com nota."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)  # cria issue + ticket
        activity.refresh_from_db()
        sync.cleanup_deleted_activity(
            release_status=DataRelease.Status.ACTIVE,
            github_repo=activity.github_repo,
            github_issue_number=activity.github_issue_number,
            glpi_ticket_id=activity.glpi_ticket_id,
            label=activity.label,
        )

    assert gh.updated == [("linea-it", "repo", 42, {"state": "closed", "state_reason": "not_planned"})]
    assert glpi.updated[-1] == (7, {"status": 6})
    assert glpi.followups[-1] == 'Atividade "Step 1" removida do plano — ticket encerrado.'


def _normalized_clients(monkeypatch):
    """Fakes com o GLPI devolvendo o HTML normalizado (risco 9 do round-trip)."""
    gh, glpi = FakeGithub(), FakeGlpi(normalize=True)
    monkeypatch.setattr("idac_drd.integrations.sync._github_client", lambda: gh)
    monkeypatch.setattr("idac_drd.integrations.sync._glpi_client", lambda: glpi)
    return gh, glpi


def test_normalized_content_does_not_trigger_resync(release, monkeypatch):
    """GLPI normaliza o HTML no GET: sync sem mudanças não reescreve nem anota."""
    gh, glpi = _normalized_clients(monkeypatch)
    with override_settings(**ENABLED):
        activity = make_activity(
            release, objectives="Criar schemas\nProcessar ingestao", status=Activity.Status.IN_PROGRESS
        )
        sync.sync_activity(activity)  # cria ticket + PUT de status
        activity.refresh_from_db()
        glpi.events.clear()
        glpi.followups.clear()
        sync.sync_activity(activity)  # nada mudou

    assert glpi.events == []
    assert glpi.followups == []


def test_normalized_content_notes_only_what_changed(release, monkeypatch):
    """Com o GET normalizado, editar notas gera nota só de notas (sem falso
    'objetivos atualizados' vindo da comparação contra o HTML do GLPI)."""
    gh, glpi = _normalized_clients(monkeypatch)
    user = User.objects.create_user(username="alice", password="pass")
    with override_settings(**ENABLED):
        activity = make_activity(release, objectives="Criar schemas", status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)
        activity.refresh_from_db()
        glpi.events.clear()
        glpi.followups.clear()
        activity.notes = "Falta o dataset de junho."
        activity.save()
        sync.sync_activity(activity, actor=user)

    assert glpi.followups == ['Atividade "Step 1" — notas atualizadas. (modificado por alice)']


def test_empty_body_uses_fallback(clients, release):
    """Sem description/objectives/notas o corpo nunca vai vazio para a API."""
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))

    assert glpi.contents[0] == "<p>Sem descrição.</p>"


def test_glpi_failure_is_logged_not_raised(clients, release, caplog):
    """Falha da API do GLPI é logada (warning), nunca quebra o fluxo."""
    gh, glpi = clients
    from idac_drd.integrations.glpi import GlpiAPIError

    def boom(*args, **kwargs):
        raise GlpiAPIError("helpdesk down")

    glpi.create_ticket = boom
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))  # todo: cria o ticket

    assert "GLPI sync failed" in caplog.text
    # o GitHub seguiu mesmo com o GLPI falhando
    assert gh.created == [("linea-it", "repo", "Step 1")]


def test_api_failure_is_logged_not_raised(clients, release, monkeypatch, caplog):
    gh, glpi = clients

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    gh.create_issue = boom
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))  # todo

    assert "GitHub sync failed" in caplog.text
    # GLPI seguiu mesmo com o GitHub falhando
    assert glpi.created == [("Release 1 - Step A: Step 1", 1)]
