// Relatório executivo do workflow em Markdown (baixado como arquivo .md).
// Consome os dados já expostos pela API: release, activities (com notes,
// blocked_reason, started_at/completed_at, mode) e as transições do release
// (quem fez o quê, quando, com qual comentário).

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

function fmtBlockquote(text) {
  if (!text) return "";
  return text
    .split("\n")
    .map((line) => `  > ${line}`)
    .join("\n");
}

function statusOf(a) {
  const status = a.status;
  if (status === "todo") return "Not started";
  if (status === "in_progress") return "In Progress";
  if (status === "blocked") return "Blocked";
  if (status === "done") return "Done";
  return status;
}

function durationOf(a) {
  if (a.duration_seconds != null) return fmtDuration(a.duration_seconds);
  if (a.started_at) return fmtDuration((Date.now() - new Date(a.started_at).getTime()) / 1000);
  return "—";
}

function releaseDuration(release, activities) {
  if (!release.started_at) return "—";
  const end =
    release.status === "completed"
      ? Math.max(
          ...activities.filter((a) => a.completed_at).map((a) => new Date(a.completed_at).getTime()),
          0,
        ) || Date.now()
      : Date.now();
  return fmtDuration((end - new Date(release.started_at).getTime()) / 1000);
}

export function buildReleaseReport(release, activities, transitions) {
  const total = activities.length;
  const done = activities.filter((a) => a.status === "done").length;
  const inProgress = activities.filter((a) => a.status === "in_progress").length;
  const blocked = activities.filter((a) => a.status === "blocked").length;
  const waiting = activities.filter((a) => a.status === "todo").length;
  const manual = activities.filter((a) => a.mode !== "nifi").length;
  const pct = total ? Math.round((100 * done) / total) : 0;

  const byActivity = new Map();
  for (const t of transitions) {
    if (!byActivity.has(t.activity)) byActivity.set(t.activity, []);
    byActivity.get(t.activity).push(t);
  }

  // dificuldades: atividades bloqueadas (agora ou em algum momento da execução)
  const difficulties = activities
    .map((a) => {
      const blockEvents = (byActivity.get(a.id) || []).filter(
        (t) => t.to_status === "blocked",
      );
      if (a.status !== "blocked" && !blockEvents.length) return null;
      const lastBlock = blockEvents[blockEvents.length - 1];
      const reason =
        a.blocked_reason ||
        lastBlock?.comment ||
        "(no reason recorded)";
      const resolved = a.status !== "blocked";
      return {
        activity: a,
        reason,
        when: fmtDate(lastBlock?.created_at),
        by: lastBlock?.actor?.name || lastBlock?.actor?.username || "—",
        resolved,
      };
    })
    .filter(Boolean);

  const lanes = (release.lanes || []).slice().sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
  const doneTimes = activities
    .filter((a) => a.duration_seconds != null)
    .map((a) => a.duration_seconds);
  const avgDuration = doneTimes.length
    ? fmtDuration(doneTimes.reduce((s, d) => s + d, 0) / doneTimes.length)
    : "—";

  const lines = [];
  lines.push(`# Workflow Report — ${release.name}`);
  lines.push("");
  lines.push(`- **Status:** ${release.status.charAt(0).toUpperCase() + release.status.slice(1)}`);
  lines.push(`- **Progress:** ${done}/${total} activities completed (${pct}%)`);
  lines.push(`- **Template:** ${release.template_key || "—"}`);
  lines.push(`- **Created:** ${fmtDate(release.created_at)} · **Started:** ${fmtDate(release.started_at)}`);
  lines.push(`- **Total duration:** ${releaseDuration(release, activities)}`);
  lines.push("");
  lines.push("## Executive Summary");
  lines.push("");
  lines.push(`- ${done} completed · ${inProgress} in progress · ${blocked} blocked · ${waiting} not started`);
  lines.push(`- ${manual} manual · ${total - manual} NiFi`);
  lines.push(
    difficulties.length
      ? `- **Difficulties:** ${difficulties.length} activity(ies) blocked at some point${
          blocked ? `, ${blocked} currently blocked` : ""
        }`
      : "- **Difficulties:** none — clean run",
  );
  lines.push(
    doneTimes.length ? `- **Average duration** per completed activity: ${avgDuration}` : "- Average duration: — (no activity completed)",
  );
  lines.push("");

  lines.push("## Difficulties");
  lines.push("");
  if (!difficulties.length) {
    lines.push("No blocked activities. All stages progressed without obstacles.");
  } else {
    for (const d of difficulties) {
      lines.push(`### ${d.activity.label} — ${d.resolved ? "was blocked (resolved)" : "blocked"}`);
      lines.push("");
      lines.push(`- Reason: ${d.reason}`);
      lines.push(`- Blocked on ${d.when} by ${d.by}`);
      lines.push("");
    }
  }

  lines.push("## Activities by Lane");
  lines.push("");
  for (const lane of lanes) {
    const laneActs = activities
      .filter((a) => a.lane === lane.id)
      .sort((x, y) => (x.order ?? 0) - (y.order ?? 0));
    if (!laneActs.length) continue;
    const laneDone = laneActs.filter((a) => a.status === "done").length;
    lines.push(`### ${lane.label} (${laneDone}/${laneActs.length} done)`);
    lines.push("");
    for (const a of laneActs) {
      lines.push(`#### ${a.label} — [${statusOf(a)}]`);
      lines.push("");
      lines.push(`- **Mode:** ${a.mode === "nifi" ? "NiFi" : "Manual"} · **Assignee:** ${a.assignee?.name || a.assignee?.username || "—"}`);
      lines.push(`- **Duration:** ${durationOf(a)}`);
      lines.push(`- **Started:** ${fmtDate(a.started_at)} · **Completed:** ${fmtDate(a.completed_at)}`);
      const timeline = (byActivity.get(a.id) || []).slice().sort((x, y) => new Date(x.created_at) - new Date(y.created_at));
      if (timeline.length) {
        lines.push("- **Timeline:**");
        for (const t of timeline) {
          const actor = t.actor?.name || t.actor?.username || "—";
          const entry = `  - ${t.from_status || "—"} → ${t.to_status} — ${actor} — ${fmtDate(t.created_at)}`;
          lines.push(t.comment ? `${entry} — "${t.comment}"` : entry);
        }
      } else {
        lines.push("- **Timeline:** not started (no transitions recorded)");
      }
      const notes = fmtBlockquote(a.notes);
      if (notes) lines.push(`- **Notes:**\n${notes}`);
      lines.push("");
    }
  }

  return lines.join("\n");
}

export function downloadReport(release, activities, transitions) {
  const md = buildReleaseReport(release, activities, transitions);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${release.slug || release.name || "release"}-workflow-report.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
