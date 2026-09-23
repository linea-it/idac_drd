// Relatório executivo do workflow em Markdown (baixado como arquivo .md).
// Consome os dados já expostos pela API: release, activities (com notes,
// blocked_reason, objectives, started_at/completed_at, mode) e as transições
// do release (quem fez o quê, quando, com qual comentário).
//
// Estrutura: 1. Report Overview · 2. Executive Summary · 3. Process Narrative
// · 4. Objectives · 5. Steps & Activities · 6. Difficulties · 7. Workload &
// Participation · 8. References · 9. Appendix (full transition log).

import { releaseStatusLabel, statusLabel, displayStatus, isObjectiveChecked, isPrereqAutoBlock } from "./activityStatus";

export function fmtDuration(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "—";
  const s = Math.round(totalSeconds);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  const parts = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (mins) parts.push(`${mins}m`);
  if (!parts.length) parts.push(`${secs}s`);
  return parts.join(" ");
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtDay(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function fmtBlockquote(text) {
  if (!text) return "";
  return text
    .split("\n")
    .map((line) => `  > ${line}`)
    .join("\n");
}

// Valor de text_before/text_after no relatório: escapa aspas (ficam dentro de
// "…") e colapsa quebras de linha para a entrada caber numa linha.
function fmtRevisionText(text) {
  return (text || "").replace(/"/g, '\\"').replace(/\s+/g, " ");
}

// Sanitiza texto livre para célula de tabela: colapsa quebras de linha e
// escapa pipes (senão a linha da tabela quebra no renderer de markdown).
function mdCell(text) {
  if (text == null) return "—";
  return String(text).replace(/\n/g, " ").replace(/\|/g, "\\|");
}

// Converte a lista de resources ({label, url}) em links markdown ([label](url)
// separados por " · "). Retorna null quando não há URLs http(s) utilizáveis.
// O label é sanitizado para não quebrar a sintaxe do link em tabelas.
export function resourcesMarkdown(resources) {
  const list = (resources || []).filter((r) => /^https?:\/\//i.test(r?.url || ""));
  if (!list.length) return null;
  return list
    .map((r) => {
      const label = ((r.label || "").trim() || r.url).replace(/[\[\]()]/g, " ");
      return `[${mdCell(label)}](${r.url})`;
    })
    .join(" · ");
}

function actorName(actor) {
  return actor?.name || actor?.username || actor?.email || "—";
}

function assigneeName(a) {
  return a.assignee?.name || a.assignee?.email || "—";
}

// Duração de execução (cycle time) de uma activity concluída, com fallback
// para dados legados sem duration_seconds preenchido.
// cycle = calendário (started_at → completed_at); effort = sessões play/pause.
function cycleSecondsOf(a) {
  if (a.duration_seconds != null) return a.duration_seconds;
  if (a.started_at && a.completed_at) return (new Date(a.completed_at) - new Date(a.started_at)) / 1000;
  return null;
}

function effortSecondsOf(a) {
  if (a.effort_seconds != null) return a.effort_seconds;
  return null;
}

// ── Métricas puras (exportadas para teste) ──────────────────────────────────

export function computeWaitTimes(activities) {
  const map = new Map();
  for (const a of activities) {
    map.set(
      a.id,
      a.started_at && a.created_at
        ? (new Date(a.started_at) - new Date(a.created_at)) / 1000
        : null,
    );
  }
  return map;
}

export function computeLeadTimes(activities) {
  const map = new Map();
  for (const a of activities) {
    map.set(
      a.id,
      a.completed_at && a.created_at
        ? (new Date(a.completed_at) - new Date(a.created_at)) / 1000
        : null,
    );
  }
  return map;
}

// Períodos de bloqueio por activity: abre na transição →blocked, fecha na
// primeira transição que sai de blocked. Re-blocks consecutivos mesclam
// (o último motivo/quem prevalece). Período sem saída fica aberto
// (endedAt=null, duração até now no render). Activity ainda blocked sem
// nenhuma transição ganha um período com start = started_at || updated_at.
export function computeBlockPeriods(activities, transitions) {
  const byActivity = new Map();
  for (const t of transitions) {
    if (!byActivity.has(t.activity)) byActivity.set(t.activity, []);
    byActivity.get(t.activity).push(t);
  }
  const periods = [];
  for (const a of activities) {
    const ts = (byActivity.get(a.id) || [])
      .slice()
      .sort((x, y) => new Date(x.created_at) - new Date(y.created_at));
    let open = null;
    for (const t of ts) {
      if (t.to_status === "blocked") {
        if (!open) {
          open = {
            activity: a,
            startedAt: t.created_at,
            endedAt: null,
            seconds: null,
            reason: t.comment || a.blocked_reason || "",
            raisedBy: t.actor || null,
          };
        } else {
          open.reason = t.comment || open.reason;
          open.raisedBy = t.actor || open.raisedBy;
        }
      } else if (open && t.from_status === "blocked" && t.to_status !== "blocked") {
        open.endedAt = t.created_at;
        open.seconds = (new Date(t.created_at) - new Date(open.startedAt)) / 1000;
        periods.push(open);
        open = null;
      }
    }
    if (open) {
      periods.push(open);
    } else if (a.status === "blocked" && !isPrereqAutoBlock(a)) {
      periods.push({
        activity: a,
        startedAt: a.started_at || a.updated_at,
        endedAt: null,
        seconds: null,
        reason: a.blocked_reason || "",
        raisedBy: null,
      });
    }
  }
  return periods;
}

export function computeCycleTimeStats(activities) {
  const items = activities
    .filter((a) => a.status === "done")
    .map((a) => ({ activity: a, seconds: cycleSecondsOf(a) }))
    .filter((x) => x.seconds != null);
  if (!items.length) return { mean: null, median: null, slowest: null, count: 0 };
  const sorted = [...items].sort((x, y) => x.seconds - y.seconds);
  const mean = sorted.reduce((s, x) => s + x.seconds, 0) / sorted.length;
  const mid = Math.floor(sorted.length / 2);
  const median =
    sorted.length % 2 ? sorted[mid].seconds : (sorted[mid - 1].seconds + sorted[mid].seconds) / 2;
  return { mean, median, slowest: sorted[sorted.length - 1], count: sorted.length };
}

export function computeDayBuckets(activities) {
  const counts = new Map();
  for (const a of activities) {
    if (a.status === "done" && a.completed_at) {
      const day = fmtDay(a.completed_at);
      counts.set(day, (counts.get(day) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort(([x], [y]) => (x < y ? -1 : 1))
    .map(([day, completed]) => ({ day, completed }));
}

export function computeAssigneeStats(activities) {
  const byKey = new Map();
  for (const a of activities) {
    const key = a.assignee?.id ?? "__unassigned__";
    if (!byKey.has(key)) {
      byKey.set(key, {
        assignee: a.assignee ? assigneeName(a) : "Unassigned",
        count: 0,
        done: 0,
        totalCycleSeconds: 0,
        totalEffortSeconds: 0,
        effortCount: 0,
      });
    }
    const row = byKey.get(key);
    row.count++;
    const effort = effortSecondsOf(a);
    if (effort != null) {
      row.totalEffortSeconds += effort;
      row.effortCount++;
    }
    if (a.status === "done") {
      row.done++;
      const s = cycleSecondsOf(a);
      if (s != null) row.totalCycleSeconds += s;
    }
  }
  return [...byKey.values()]
    .map((r) => ({
      ...r,
      avgCycleSeconds: r.done ? r.totalCycleSeconds / r.done : null,
      avgEffortSeconds: r.effortCount ? r.totalEffortSeconds / r.effortCount : null,
    }))
    .sort((x, y) => y.count - x.count);
}

const ACTOR_CATEGORY = { in_progress: "started", in_review: "reviewed", blocked: "blocked", done: "completed" };

export function computeActorStats(transitions) {
  const byKey = new Map();
  for (const t of transitions) {
    const key = t.actor?.id ?? `__null__:${t.actor?.username || ""}`;
    if (!byKey.has(key)) {
      byKey.set(key, {
        actor: actorName(t.actor),
        started: 0,
        reviewed: 0,
        blocked: 0,
        completed: 0,
        other: 0,
        total: 0,
      });
    }
    const row = byKey.get(key);
    row[ACTOR_CATEGORY[t.to_status] || "other"]++;
    row.total++;
  }
  return [...byKey.values()].sort((x, y) => y.total - x.total);
}

export function computeStepStats(release, activities, waitTimes, blockPeriods) {
  return (release.steps || []).map((step) => {
    const acts = activities.filter((a) => a.step === step.id);
    const done = acts.filter((a) => a.status === "done");
    const cycles = done.map(cycleSecondsOf).filter((s) => s != null);
    const efforts = acts.map(effortSecondsOf).filter((s) => s != null);
    const waits = acts.map((a) => waitTimes.get(a.id)).filter((s) => s != null);
    const stepBlocks = blockPeriods.filter((p) => p.activity.step === step.id);
    const blockSeconds = stepBlocks
      .map((p) =>
        p.seconds ??
        (p.endedAt ? null : (Date.now() - new Date(p.startedAt).getTime()) / 1000),
      )
      .filter((s) => s != null);
    return {
      step,
      total: acts.length,
      done: done.length,
      pct: acts.length ? Math.round((100 * done.length) / acts.length) : 0,
      avgCycleSeconds: cycles.length ? cycles.reduce((s, d) => s + d, 0) / cycles.length : null,
      avgEffortSeconds: efforts.length ? efforts.reduce((s, d) => s + d, 0) / efforts.length : null,
      avgWaitSeconds: waits.length ? waits.reduce((s, d) => s + d, 0) / waits.length : null,
      blockedCount: stepBlocks.length,
      avgBlockSeconds: blockSeconds.length
        ? blockSeconds.reduce((s, d) => s + d, 0) / blockSeconds.length
        : null,
    };
  });
}

export function computeDependencyStats(activities) {
  const byId = new Map(activities.map((a) => [a.id, a]));
  const list = activities
    .filter((a) => a.locked)
    .map((a) => ({
      activity: a,
      dependsOnLabels: (a.depends_on || []).map((id) => byId.get(id)?.label || "—"),
      prereqMet: a.prerequisites_met,
      locked: a.locked,
    }));
  return { lockedCount: list.length, list };
}

export function refsOf(activity) {
  const repo = activity.github_repo || null;
  const issue = activity.github_issue_number ?? null;
  let github = null;
  if (repo && issue != null) github = `${repo}#${issue}`;
  else if (repo) github = repo;
  else if (issue != null) github = `#${issue}`;
  return {
    github,
    glpi: activity.glpi_ticket_id ? `#${activity.glpi_ticket_id}` : null,
    external: activity.external_ref || null,
  };
}

export function computeReleaseDuration(release, activities) {
  if (!release.started_at) return null;
  const completedTimes = activities
    .filter((a) => a.completed_at)
    .map((a) => new Date(a.completed_at).getTime());
  if (release.status === "completed") {
    const end = completedTimes.length ? Math.max(...completedTimes) : Date.now();
    return (end - new Date(release.started_at).getTime()) / 1000;
  }
  return (Date.now() - new Date(release.started_at).getTime()) / 1000;
}

// ── Timeline e renderização ─────────────────────────────────────────────────

export function buildTimeline(release, transitions) {
  const events = [];
  if (release.started_at) {
    events.push({ at: new Date(release.started_at), day: fmtDay(release.started_at), kind: "release_started" });
  }
  for (const t of transitions) {
    events.push({ at: new Date(t.created_at), day: fmtDay(t.created_at), kind: "transition", transition: t });
  }
  return events.sort((x, y) => x.at - y.at);
}

function groupTransitionsByActivity(transitions) {
  const map = new Map();
  for (const t of transitions) {
    if (!map.has(t.activity)) map.set(t.activity, []);
    map.get(t.activity).push(t);
  }
  return map;
}

function groupTextRevisionsByActivity(textRevisions) {
  const map = new Map();
  const sorted = [...textRevisions].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  for (const r of sorted) {
    if (!map.has(r.activity)) map.set(r.activity, []);
    map.get(r.activity).push(r);
  }
  return map;
}

export function renderReportHeader(release, activities, durationSeconds) {
  const total = activities.length;
  const done = activities.filter((a) => a.status === "done").length;
  const pct = total ? Math.round((100 * done) / total) : 0;
  return [
    `# ${release.name} — Workflow Report`,
    `> Generated on ${fmtDate(new Date().toISOString())} · slug: ${release.slug}`,
    "",
    "## 1. Report Overview",
    "",
    "| Field | Value |",
    "|---|---|",
    `| Name | ${mdCell(release.name)} |`,
    `| Status | ${mdCell(releaseStatusLabel(release.status))} |`,
    `| Workflow template | ${mdCell(release.template_key || "—")} |`,
    `| Created | ${fmtDate(release.created_at)} |`,
    `| Started | ${fmtDate(release.started_at)} |`,
    `| Archived | ${fmtDate(release.archived_at)} |`,
    `| Total activities | ${total} |`,
    `| Completed | ${done} (${pct}%) |`,
    `| Total duration | ${durationSeconds != null ? fmtDuration(durationSeconds) : "—"} |`,
  ];
}

export function renderExecutiveSummary(release, activities, metrics) {
  const { counts, cycleStats, waitTimes, blockPeriods, dayBuckets, assigneeStats, dependencyStats, durationSeconds } = metrics;
  const pct = counts.total ? Math.round((100 * counts.done) / counts.total) : 0;
  const lines = ["## 2. Executive Summary", ""];
  lines.push(`- **Status:** ${releaseStatusLabel(release.status)}`);
  lines.push(`- **Outcome:** ${counts.done}/${counts.total} activities completed (${pct}%)`);
  if (release.started_at) {
    const completedTimes = activities
      .filter((a) => a.completed_at)
      .map((a) => new Date(a.completed_at).getTime());
    const endAt = completedTimes.length ? Math.max(...completedTimes) : Date.now();
    lines.push(
      `- **Timeline:** ${fmtDate(release.started_at)} → ${fmtDate(new Date(endAt).toISOString())} · total ${fmtDuration(durationSeconds)}`,
    );
  } else {
    lines.push("- **Timeline:** not started");
  }
  if (cycleStats.count) {
    lines.push(
      `- **Throughput:** average cycle time ${fmtDuration(cycleStats.mean)} per completed activity · median ${fmtDuration(cycleStats.median)} · slowest: ${cycleStats.slowest.activity.label} (${fmtDuration(cycleStats.slowest.seconds)})`,
    );
  } else {
    lines.push("- **Throughput:** no completed activity");
  }
  const efforts = activities.map(effortSecondsOf).filter((s) => s != null);
  if (efforts.length) {
    const totalEffort = efforts.reduce((s, d) => s + d, 0);
    lines.push(
      `- **Effort (play time):** total ${fmtDuration(totalEffort)} across ${efforts.length} activit${efforts.length === 1 ? "y" : "ies"} with timed sessions · average ${fmtDuration(totalEffort / efforts.length)}`,
    );
  } else {
    lines.push("- **Effort (play time):** no work sessions recorded");
  }
  const waits = activities.map((a) => waitTimes.get(a.id)).filter((s) => s != null);
  lines.push(
    waits.length
      ? `- **Waiting:** average ${fmtDuration(waits.reduce((s, d) => s + d, 0) / waits.length)} between creation and first start`
      : "- **Waiting:** — (no activity started)",
  );
  const blockedTotal = blockPeriods.reduce(
    (s, p) => s + (p.seconds ?? Math.max(0, (Date.now() - new Date(p.startedAt).getTime()) / 1000)),
    0,
  );
  lines.push(
    `- **Blocking:** ${blockPeriods.length} activity${blockPeriods.length === 1 ? "" : "ies"} blocked at some point · ${counts.blocked} currently blocked · ${fmtDuration(blockedTotal)} total blocked time`,
  );
  lines.push(
    assigneeStats.length
      ? `- **Workload:** ${assigneeStats.length} assignee${assigneeStats.length === 1 ? "" : "s"} · highest load: ${assigneeStats[0].assignee} (${assigneeStats[0].count} activity${assigneeStats[0].count === 1 ? "" : "ies"})`
      : "- **Workload:** no assignees",
  );
  lines.push(`- **Modes:** ${counts.manual} manual · ${counts.nifi} NiFi`);
  if (release.status === "active") {
    lines.push(
      `- **Remaining:** ${counts.todo} to do · ${counts.waiting} waiting · ${counts.inProgress} in progress · ${counts.inReview} in review`,
    );
  }
  lines.push(
    `- **Dependencies:** ${dependencyStats.lockedCount} activity${dependencyStats.lockedCount === 1 ? "" : "ies"} currently locked by unmet prerequisites`,
  );
  lines.push(
    `- **Coverage:** ${counts.withoutAssignee} activity${counts.withoutAssignee === 1 ? "" : "ies"} without assignee · ${counts.withoutRefs} activity${counts.withoutRefs === 1 ? "" : "ies"} without external references`,
  );
  if (dayBuckets.length) {
    lines.push("", "#### Progress over time", "", "| Date | Completed | Cumulative | % |", "|---|---|---|---|");
    let cumulative = 0;
    for (const b of dayBuckets) {
      cumulative += b.completed;
      lines.push(
        `| ${b.day} | ${b.completed} | ${cumulative} | ${counts.total ? Math.round((100 * cumulative) / counts.total) : 0}% |`,
      );
    }
  }
  return lines;
}

export function renderProcessNarrative(release, timeline, activities) {
  const lines = ["## 3. Process Narrative", ""];
  if (!release.started_at) {
    lines.push(`This release has not started yet. Created on ${fmtDate(release.created_at)}.`);
    return lines;
  }
  const stepByActivity = new Map(activities.map((a) => [a.id, a.step_label]));
  let currentDay = null;
  for (const ev of timeline) {
    if (ev.day !== currentDay) {
      lines.push(`### ${ev.day}`);
      currentDay = ev.day;
    }
    const time = fmtDate(ev.at.toISOString()).slice(11);
    if (ev.kind === "release_started") {
      lines.push(`- **${time}** — Release started`);
    } else {
      const t = ev.transition;
      const step = stepByActivity.get(t.activity) || "—";
      const from = t.from_status ? statusLabel(t.from_status) : "started";
      let line = `- **${time}** — ${step} · ${t.activity_label}: ${from} → ${statusLabel(t.to_status)} (${actorName(t.actor)})`;
      if (t.comment) line += ` — "${t.comment}"`;
      lines.push(line);
    }
  }
  return lines;
}

export function renderObjectives(release, activities) {
  const lines = ["## 4. Objectives", ""];
  const steps = (release.steps || []).slice().sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
  let any = false;
  for (const step of steps) {
    const acts = activities
      .filter((a) => a.step === step.id && a.objectives)
      .sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
    if (!acts.length) continue;
    any = true;
    lines.push(`### ${step.label}`);
    lines.push("");
    for (const a of acts) {
      lines.push(`#### ${a.label}`);
      lines.push("");
      for (const obj of a.objectives.split("\n").map((s) => s.trim()).filter(Boolean)) {
        // o prefixo [x]/[ ] é de persistência (tickets); o relatório decide a marcação
        lines.push(`- [${isObjectiveChecked(obj, a.status) ? "x" : " "}] ${obj.replace(/^\[[x ]\]\s*/, "")}`);
      }
      lines.push("");
    }
  }
  if (!any) lines.push("No objectives recorded.");
  return lines;
}

export function renderStepsAndActivities(release, activities, ctx) {
  const { waitTimes, leadTimes, blockPeriods, transitionsByActivity, stepStats, textRevisionsByActivity } = ctx;
  const byId = new Map(activities.map((a) => [a.id, a]));
  const lines = ["## 5. Steps & Activities", ""];
  if (!activities.length) {
    lines.push("No activities recorded.");
    return lines;
  }
  lines.push("| Step | Total | Done | % | Avg cycle | Avg effort | Avg wait | Blocked | Avg blocked time |");
  lines.push("|---|---|---|---|---|---|---|---|---|");
  for (const s of stepStats) {
    lines.push(
      `| ${mdCell(s.step.label)} | ${s.total} | ${s.done} | ${s.pct}% | ${s.avgCycleSeconds != null ? fmtDuration(s.avgCycleSeconds) : "—"} | ${s.avgEffortSeconds != null ? fmtDuration(s.avgEffortSeconds) : "—"} | ${s.avgWaitSeconds != null ? fmtDuration(s.avgWaitSeconds) : "—"} | ${s.blockedCount} | ${s.avgBlockSeconds != null ? fmtDuration(s.avgBlockSeconds) : "—"} |`,
    );
  }
  lines.push("");
  const steps = (release.steps || []).slice().sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
  for (const step of steps) {
    const acts = activities
      .filter((a) => a.step === step.id)
      .sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
    if (!acts.length) continue;
    lines.push(`### ${step.label}`);
    const stepLinks = resourcesMarkdown(step.resources);
    if (stepLinks) lines.push(`- **Links:** ${stepLinks}`);
    lines.push("");
    for (const a of acts) {
      lines.push(`#### ${a.label} — [${statusLabel(displayStatus(a))}]`);
      lines.push("");
      lines.push(`- **Step:** ${mdCell(step.label)} · **Mode:** ${a.mode === "nifi" ? "NiFi" : "Manual"}`);
      lines.push(`- **Assignee:** ${assigneeName(a)} · **Size:** ${mdCell(a.size || "—")} · **Area:** ${mdCell(a.area || "—")}`);
      const refs = refsOf(a);
      lines.push(`- **References:** ${refs.github || "—"} · ${refs.glpi || "—"} · ${refs.external || "—"}`);
      const resLinks = resourcesMarkdown(a.resources);
      if (resLinks) lines.push(`- **Links:** ${resLinks}`);
      const depLabels = (a.depends_on || []).map((id) => byId.get(id)?.label || "—").join(", ") || "—";
      lines.push(`- **Dependencies:** ${mdCell(depLabels)} · **Prerequisites met:** ${a.prerequisites_met ? "yes" : "no"} · **Locked:** ${a.locked ? "yes" : "no"}`);
      const cycle = cycleSecondsOf(a) != null
        ? fmtDuration(cycleSecondsOf(a))
        : a.started_at
          ? `${fmtDuration((Date.now() - new Date(a.started_at).getTime()) / 1000)} (in progress)`
          : "—";
      const effort = effortSecondsOf(a) != null ? fmtDuration(effortSecondsOf(a)) : "—";
      const wait = waitTimes.get(a.id) != null ? fmtDuration(waitTimes.get(a.id)) : "—";
      const lead = leadTimes.get(a.id) != null ? fmtDuration(leadTimes.get(a.id)) : "—";
      lines.push(
        `- **Timeline:** created ${fmtDate(a.created_at)} → started ${fmtDate(a.started_at)} → completed ${fmtDate(a.completed_at)} · cycle ${cycle} · effort ${effort} · wait ${wait} · lead ${lead}`,
      );
      const timeline = transitionsByActivity.get(a.id) || [];
      if (timeline.length) {
        lines.push("- **Status history:**");
        for (const t of timeline) {
          const from = t.from_status ? statusLabel(t.from_status) : "started";
          let entry = `  - ${from} → ${statusLabel(t.to_status)} — ${actorName(t.actor)} — ${fmtDate(t.created_at)}`;
          if (t.comment) entry += ` — "${t.comment}"`;
          lines.push(entry);
        }
      }
      const desc = fmtBlockquote(a.description);
      if (desc) lines.push(`- **Description:**\n${desc}`);
      const notes = fmtBlockquote(a.notes);
      if (notes) lines.push(`- **Notes:**\n${notes}`);
      const textRevs = textRevisionsByActivity.get(a.id) || [];
      if (textRevs.length) {
        lines.push("- **Text revisions:**");
        for (const r of textRevs) {
          lines.push(
            `  - ${r.field} — ${actorName(r.actor)} — ${fmtDate(r.created_at)} — "${fmtRevisionText(r.text_before)}" → "${fmtRevisionText(r.text_after)}"`,
          );
        }
      }
      lines.push("");
    }
  }
  return lines;
}

export function renderDifficulties(activities, blockPeriods) {
  const lines = ["## 6. Difficulties", ""];
  if (!blockPeriods.length) {
    lines.push("No blocked periods. All activities progressed without obstacles.");
    return lines;
  }
  lines.push("| Activity | Blocked from | Resolved at | Duration | Reason | Raised by |");
  lines.push("|---|---|---|---|---|---|");
  for (const p of blockPeriods) {
    const open = p.endedAt == null;
    const seconds = p.seconds ?? (open ? (Date.now() - new Date(p.startedAt).getTime()) / 1000 : null);
    const duration = seconds != null ? fmtDuration(seconds) : "—";
    lines.push(
      `| ${mdCell(p.activity.label)} | ${fmtDate(p.startedAt)} | ${fmtDate(p.endedAt)} | ${open ? `${duration} (still blocked)` : duration} | ${mdCell(p.reason || "(no reason recorded)")} | ${actorName(p.raisedBy)} |`,
    );
  }
  const longReasons = blockPeriods.filter(
    (p) => p.reason && (p.reason.includes("\n") || p.reason.length > 80),
  );
  if (longReasons.length) {
    lines.push("");
    for (const p of longReasons) {
      lines.push(`#### ${p.activity.label}`);
      lines.push("");
      lines.push(fmtBlockquote(p.reason));
      lines.push("");
    }
  }
  return lines;
}

export function renderWorkload(activities, assigneeStats, actorStats) {
  const lines = ["## 7. Workload & Participation", ""];
  if (!activities.length) {
    lines.push("No activities recorded.");
    return lines;
  }
  lines.push(
    "#### Workload by assignee",
    "",
    "Cycle = calendar time (started → completed). Effort = active play/pause sessions.",
    "",
    "| Assignee | Activities | Completed | Total cycle | Avg cycle | Total effort | Avg effort |",
    "|---|---|---|---|---|---|---|",
  );
  for (const r of assigneeStats) {
    lines.push(
      `| ${mdCell(r.assignee)} | ${r.count} | ${r.done} | ${r.done ? fmtDuration(r.totalCycleSeconds) : "—"} | ${r.avgCycleSeconds != null ? fmtDuration(r.avgCycleSeconds) : "—"} | ${r.effortCount ? fmtDuration(r.totalEffortSeconds) : "—"} | ${r.avgEffortSeconds != null ? fmtDuration(r.avgEffortSeconds) : "—"} |`,
    );
  }
  lines.push(
    "",
    "#### Participation (transition actors)",
    "",
    "| Actor | Started | Reviewed | Blocked | Completed | Other | Total |",
    "|---|---|---|---|---|---|---|",
  );
  for (const r of actorStats) {
    lines.push(
      `| ${mdCell(r.actor)} | ${r.started} | ${r.reviewed} | ${r.blocked} | ${r.completed} | ${r.other} | ${r.total} |`,
    );
  }
  return lines;
}

export function renderReferences(activities) {
  const lines = ["## 8. References & Links", ""];
  const withRefs = activities.filter((a) => {
    const r = refsOf(a);
    return r.github || r.glpi || r.external || resourcesMarkdown(a.resources);
  });
  if (!withRefs.length) {
    lines.push("No references or links recorded.");
    return lines;
  }
  lines.push(
    "| Activity | GitHub | GLPI | External ref | Links |",
    "|---|---|---|---|---|",
  );
  for (const a of withRefs) {
    const r = refsOf(a);
    lines.push(
      `| ${mdCell(a.label)} | ${mdCell(r.github || "—")} | ${mdCell(r.glpi || "—")} | ${mdCell(r.external || "—")} | ${resourcesMarkdown(a.resources) || "—"} |`,
    );
  }
  return lines;
}

export function renderTransitionLog(transitions) {
  const lines = ["## 9. Appendix — Full Transition Log", ""];
  if (!transitions.length) {
    lines.push("No transitions recorded.");
    return lines;
  }
  lines.push("| Date | Actor | Activity | From | To | Comment |", "|---|---|---|---|---|---|");
  for (const t of transitions) {
    const from = t.from_status ? statusLabel(t.from_status) : "started";
    lines.push(
      `| ${fmtDate(t.created_at)} | ${mdCell(actorName(t.actor))} | ${mdCell(t.activity_label)} | ${from} | ${statusLabel(t.to_status)} | ${mdCell(t.comment || "—")} |`,
    );
  }
  return lines;
}

// ── API pública ─────────────────────────────────────────────────────────────

export function buildReleaseReport(release, activities, transitions, textRevisions = []) {
  const sortedTransitions = [...transitions].sort(
    (a, b) => new Date(a.created_at) - new Date(b.created_at),
  );
  const durationSeconds = computeReleaseDuration(release, activities);
  const counts = {
    total: activities.length,
    done: activities.filter((a) => a.status === "done").length,
    inProgress: activities.filter((a) => a.status === "in_progress").length,
    inReview: activities.filter((a) => a.status === "in_review").length,
    blocked: activities.filter((a) => displayStatus(a) === "blocked").length,
    waiting: activities.filter((a) => displayStatus(a) === "waiting").length,
    todo: activities.filter((a) => displayStatus(a) === "todo").length,
    manual: activities.filter((a) => a.mode !== "nifi").length,
    nifi: activities.filter((a) => a.mode === "nifi").length,
    withoutAssignee: activities.filter((a) => !a.assignee).length,
    withoutRefs: activities.filter(
      (a) => !a.github_repo && !a.github_issue_number && !a.glpi_ticket_id && !a.external_ref,
    ).length,
  };
  const metrics = {
    durationSeconds,
    counts,
    waitTimes: computeWaitTimes(activities),
    leadTimes: computeLeadTimes(activities),
    blockPeriods: computeBlockPeriods(activities, sortedTransitions),
    cycleStats: computeCycleTimeStats(activities),
    dayBuckets: computeDayBuckets(activities),
    assigneeStats: computeAssigneeStats(activities),
    actorStats: computeActorStats(sortedTransitions),
    dependencyStats: computeDependencyStats(activities),
  };
  metrics.stepStats = computeStepStats(release, activities, metrics.waitTimes, metrics.blockPeriods);
  const ctx = {
    ...metrics,
    transitionsByActivity: groupTransitionsByActivity(sortedTransitions),
    textRevisionsByActivity: groupTextRevisionsByActivity(textRevisions),
  };
  const timeline = buildTimeline(release, sortedTransitions);

  return [
    ...renderReportHeader(release, activities, durationSeconds),
    "",
    ...renderExecutiveSummary(release, activities, ctx),
    "",
    ...renderProcessNarrative(release, timeline, activities),
    "",
    ...renderObjectives(release, activities),
    "",
    ...renderStepsAndActivities(release, activities, ctx),
    "",
    ...renderDifficulties(activities, metrics.blockPeriods),
    "",
    ...renderWorkload(activities, metrics.assigneeStats, metrics.actorStats),
    "",
    ...renderReferences(activities),
    "",
    ...renderTransitionLog(sortedTransitions),
  ].join("\n");
}

export function downloadTextFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadReport(release, activities, transitions, textRevisions = []) {
  const md = buildReleaseReport(release, activities, transitions, textRevisions);
  downloadTextFile(`${release.slug || release.name || "release"}-workflow-report.md`, md, "text/markdown;charset=utf-8");
}
