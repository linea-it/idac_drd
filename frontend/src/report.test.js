// Testes do gerador de relatório Markdown (report.js).
// Funções puras — sem mocks de API. Nunca assertar literais de data/hora:
// o esperado é computado com fmtDate/fmtDuration para não depender de TZ.

import { afterEach, describe, expect, it, vi } from "vitest";
import { buildReleaseReport, downloadReport, fmtDate, fmtDuration, renderObjectives } from "./report";

describe("buildReleaseReport", () => {
  it("draft sem atividades", () => {
    const release = {
      name: "Draft Release",
      slug: "draft-release",
      status: "draft",
      template_key: "template-x",
      started_at: null,
      archived_at: null,
      created_at: "2026-08-10T09:00:00Z",
      steps: [],
    };
    const md = buildReleaseReport(release, [], []);
    expect(md).toContain("# Draft Release — Workflow Report");
    expect(md).toContain("## 1. Report Overview");
    expect(md).toContain("## 2. Executive Summary");
    expect(md).toContain("**Status:** Draft");
    expect(md).toContain("0/0");
    expect(md).toContain("has not started");
    expect(md).toContain("## 4. Objectives");
    expect(md).toContain("No objectives recorded.");
    expect(md).toContain("## 9. Appendix — Full Transition Log");
  });

  it("execução completa com bloqueio resolvido", () => {
    const jane = { id: 1, username: "jane", name: "Jane Doe", email: "jane@example.com" };
    const alice = { id: 2, username: "alice", name: "Alice", email: "alice@example.com" };
    const steps = [
      { id: 10, key: "collection", label: "Data Collection", order: 0 },
      {
        id: 20,
        key: "validation",
        label: "Validation",
        order: 1,
        resources: [{ label: "Schema docs", url: "https://docs.google.com/d/schema" }],
      },
    ];
    const activities = [
      {
        id: 1, key: "load", label: "Load raw feed", description: "",
        objectives: "Load raw feed\nNormalize columns", order: 0, step: 10,
        step_key: "collection", step_label: "Data Collection", status: "done",
        resources: [{ label: "Setup guide", url: "https://docs.google.com/d/abc" }],
        assignee: jane, blocked_reason: "", mode: "manual", notes: "",
        external_ref: "", github_repo: "acme/ds", github_issue_number: 123,
        glpi_ticket_id: null, area: "", size: "", depends_on: [],
        prerequisites_met: true, locked: false,
        started_at: "2026-08-15T10:00:00Z", completed_at: "2026-08-15T11:30:00Z",
        duration_seconds: 5400, created_at: "2026-08-15T09:00:00Z",
      },
      {
        id: 2, key: "validate", label: "Validate schema", description: "",
        objectives: "Validate schema", order: 0, step: 20,
        step_key: "validation", step_label: "Validation", status: "done",
        assignee: alice, blocked_reason: "missing API token", mode: "manual",
        notes: "", external_ref: "", github_repo: "", github_issue_number: null,
        glpi_ticket_id: 45, area: "", size: "", depends_on: [],
        prerequisites_met: true, locked: false,
        started_at: "2026-08-15T12:00:00Z", completed_at: "2026-08-16T10:00:00Z",
        duration_seconds: null, created_at: "2026-08-15T08:00:00Z",
      },
      {
        id: 3, key: "publish", label: "Publish dataset", description: "",
        objectives: "", order: 1, step: 20, step_key: "validation",
        step_label: "Validation", status: "todo", assignee: null,
        blocked_reason: "", mode: "manual", notes: "", external_ref: "",
        github_repo: "", github_issue_number: null, glpi_ticket_id: null,
        area: "", size: "", depends_on: [1], prerequisites_met: false,
        locked: true, started_at: null, completed_at: null,
        duration_seconds: null, created_at: "2026-08-15T08:00:00Z",
      },
    ];
    const transitions = [
      {
        id: 1, activity: 2, activity_label: "Validate schema",
        from_status: "todo", to_status: "in_progress", actor: alice,
        comment: "", created_at: "2026-08-15T12:00:00Z",
      },
      {
        id: 2, activity: 2, activity_label: "Validate schema",
        from_status: "in_progress", to_status: "blocked", actor: alice,
        comment: "missing API token", created_at: "2026-08-15T12:30:00Z",
      },
      {
        id: 3, activity: 2, activity_label: "Validate schema",
        from_status: "blocked", to_status: "in_progress", actor: alice,
        comment: "token issued", created_at: "2026-08-16T09:00:00Z",
      },
      {
        id: 4, activity: 2, activity_label: "Validate schema",
        from_status: "in_progress", to_status: "done", actor: alice,
        comment: "", created_at: "2026-08-16T10:00:00Z",
      },
    ];
    const release = {
      name: "Sprint Release",
      slug: "sprint-release",
      status: "completed",
      template_key: "idac-br",
      started_at: "2026-08-15T09:00:00Z",
      archived_at: null,
      created_at: "2026-08-14T09:00:00Z",
      steps,
    };
    const md = buildReleaseReport(release, activities, transitions);

    expect(md).toContain("**Outcome:** 2/3 activities completed (67%)");
    expect(md).toContain("1 activity blocked at some point");
    expect(md).toContain("0 currently blocked");
    // período de bloqueio 12:30 → 09:00 do dia seguinte = 20h30m
    expect(md).toContain(fmtDuration(73800));
    expect(md).toContain("- [x] Load raw feed");
    expect(md).toContain("- [x] Normalize columns");
    expect(md).toContain("- [x] Validate schema");
    expect(md).toContain("acme/ds#123");
    expect(md).toContain("#45");
    // wait time de act1: created 09:00 → started 10:00 = 1h
    expect(md).toContain(fmtDuration(3600));
    expect(md).toContain("missing API token");
    expect(md).toContain("1 activity currently locked");
    expect(md).toContain("Jane Doe");
    expect(md).toContain("Alice");
    // resources: no detail da activity (seção 5), no header do step e na seção 8
    expect(md).toContain("[Setup guide](https://docs.google.com/d/abc)");
    expect(md).toContain("[Schema docs](https://docs.google.com/d/schema)");
    expect(md).toContain("## 8. References & Resources");
    expect(md).toContain("## 9. Appendix — Full Transition Log");
    expect(md).toContain("token issued");
  });

  it("objetivos com colchetes de persistência não duplicam a marcação", () => {
    const release = { slug: "r1", steps: [{ id: 1, label: "Ingestão", order: 0 }] };
    const activities = [
      {
        id: 1, label: "Ingerir", step: 1, status: "done", order: 0,
        objectives: "[x] Criar schemas\n[ ] Processar ingestao",
      },
    ];
    const md = renderObjectives(release, activities).join("\n");
    expect(md).toContain("- [x] Criar schemas");
    expect(md).not.toContain("[x] [x]");
  });

  it("em execução usa durações parciais até now", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-20T12:00:00Z"));
    const release = {
      name: "Active Release",
      slug: "active-release",
      status: "active",
      template_key: "",
      started_at: "2026-08-16T10:00:00Z",
      archived_at: null,
      created_at: "2026-08-16T09:00:00Z",
      steps: [],
    };
    const activities = [
      {
        id: 1, key: "a1", label: "Running task", description: "",
        objectives: "", order: 0, step: null, step_key: "", step_label: "",
        status: "in_progress", assignee: null, blocked_reason: "",
        mode: "manual", notes: "", external_ref: "", github_repo: "",
        github_issue_number: null, glpi_ticket_id: null, area: "", size: "",
        depends_on: [], prerequisites_met: true, locked: false,
        started_at: "2026-08-16T10:00:00Z", completed_at: null,
        duration_seconds: null, created_at: "2026-08-16T09:00:00Z",
      },
    ];
    const md = buildReleaseReport(release, activities, []);
    const expected = fmtDuration(
      (new Date("2026-08-20T12:00:00Z") - new Date("2026-08-16T10:00:00Z")) / 1000,
    );
    expect(md).toContain(expected);
    expect(md).toContain("0 to do · 1 in progress · 0 in review");
  });

  it("seção 5 inclui as text revisions por atividade (e o default não renderiza a subseção)", () => {
    const release = {
      name: "Rel",
      slug: "rel",
      status: "active",
      template_key: "",
      started_at: null,
      archived_at: null,
      created_at: "2026-08-15T09:00:00Z",
      steps: [{ id: 1, label: "Ingestão", order: 0 }],
    };
    const activities = [
      {
        id: 1, key: "a1", label: "Ingerir", description: "", objectives: "",
        order: 0, step: 1, step_key: "ingestao", step_label: "Ingestão",
        status: "todo", assignee: null, blocked_reason: "", mode: "manual",
        notes: "", external_ref: "", github_repo: "", github_issue_number: null,
        glpi_ticket_id: null, area: "", size: "", depends_on: [],
        prerequisites_met: true, locked: false, started_at: null,
        completed_at: null, duration_seconds: null, created_at: "2026-08-15T09:00:00Z",
      },
    ];
    const textRevisions = [
      {
        id: 1, activity: 1, field: "notes",
        text_before: "nota\ncom quebra", text_after: "nota nova",
        actor: { id: 2, username: "alice" }, created_at: "2026-08-16T10:00:00Z",
      },
      {
        id: 2, activity: 1, field: "notes",
        text_before: "nota nova", text_after: "",
        actor: { id: 2, username: "alice" }, created_at: "2026-08-17T10:00:00Z",
      },
    ];

    const withRevs = buildReleaseReport(release, activities, [], textRevisions);
    expect(withRevs).toContain("- **Text revisions:**");
    // quebras de linha colapsam; campo vazio vira ""
    expect(withRevs).toContain(`- notes — alice — ${fmtDate("2026-08-16T10:00:00Z")} — "nota com quebra" → "nota nova"`);
    expect(withRevs).toContain(`- notes — alice — ${fmtDate("2026-08-17T10:00:00Z")} — "nota nova" → ""`);

    // chamada de 3 args segue o default (sem subseção)
    const withoutRevs = buildReleaseReport(release, activities, []);
    expect(withoutRevs).not.toContain("Text revisions");
  });
});

describe("downloadReport", () => {
  it("gera blob markdown e nome de arquivo com o slug", () => {
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    const appendSpy = vi.spyOn(document.body, "appendChild");
    const release = {
      name: "Rel",
      slug: "rel-slug",
      status: "draft",
      template_key: "",
      started_at: null,
      archived_at: null,
      created_at: "2026-08-15T09:00:00Z",
      steps: [],
    };
    downloadReport(release, [], []);

    const blob = URL.createObjectURL.mock.calls[0][0];
    expect(blob.type).toBe("text/markdown;charset=utf-8");
    const anchor = appendSpy.mock.calls[0][0];
    expect(anchor.download).toBe("rel-slug-workflow-report.md");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
  });

  it("repassa as text revisions ao conteúdo do blob", async () => {
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    const release = {
      name: "Rel",
      slug: "rel-slug",
      status: "active",
      template_key: "",
      started_at: null,
      archived_at: null,
      created_at: "2026-08-15T09:00:00Z",
      steps: [{ id: 1, label: "Ingestão", order: 0 }],
    };
    const activities = [
      {
        id: 1, key: "a1", label: "Ingerir", description: "", objectives: "",
        order: 0, step: 1, step_key: "ingestao", step_label: "Ingestão",
        status: "todo", assignee: null, blocked_reason: "", mode: "manual",
        notes: "", external_ref: "", github_repo: "", github_issue_number: null,
        glpi_ticket_id: null, area: "", size: "", depends_on: [],
        prerequisites_met: true, locked: false, started_at: null,
        completed_at: null, duration_seconds: null, created_at: "2026-08-15T09:00:00Z",
      },
    ];
    downloadReport(release, activities, [], [
      {
        id: 1, activity: 1, field: "description",
        text_before: "", text_after: "nova desc",
        actor: { id: 2, username: "alice" }, created_at: "2026-08-16T10:00:00Z",
      },
    ]);

    const blob = URL.createObjectURL.mock.calls[0][0];
    expect(await blob.text()).toContain("- **Text revisions:**");
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
