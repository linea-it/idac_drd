// Status efetivo para exibição.
// O backend materializa gate de deps como status="blocked" + motivo
// "Waiting on prerequisites: …" (_block_until_prerequisites). Isso NÃO é
// bloqueio manual — na UI aparece como "waiting". Bloqueio manual (motivo
// livre) permanece "blocked".
const PREREQ_BLOCK_PREFIXES = ["Waiting on prerequisites", "Aguardando pré-requisitos"];

export function isPrereqAutoBlock(activity) {
  if (activity.status !== "blocked") return false;
  const reason = activity.blocked_reason || "";
  // legado: blocked sem motivo com deps pendentes também era auto
  if (!reason.trim()) return !activity.prerequisites_met;
  return PREREQ_BLOCK_PREFIXES.some((p) => reason.startsWith(p));
}

export function displayStatus(activity) {
  if (activity.status === "todo" && !activity.prerequisites_met) return "waiting";
  if (isPrereqAutoBlock(activity)) return "waiting";
  return activity.status;
}

// Travada na UI (cadeado): Waiting (deps) OU Blocked (manual).
// Não misturar com o campo API `locked` (só gate de deps — legado do relatório).
export function isStuck(activity) {
  const s = displayStatus(activity);
  return s === "waiting" || s === "blocked";
}

// Rótulos humanizados dos chips de status (sem underscore, capitalizados).
const STATUS_LABELS = {
  todo: "To do",
  waiting: "Waiting",
  in_progress: "In Progress",
  paused: "Paused",
  in_review: "In review",
  done: "Done",
  blocked: "Blocked",
};

export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

export function objectiveItems(objectives) {
  return (objectives || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

// [x] está feito. [ ] está aberto. Sem colchete, done legado conta como feito.
export function isObjectiveChecked(line, status) {
  const text = (line || "").trim();
  if (/^\[x\]/i.test(text)) return true;
  if (/^\[[ ]\]/i.test(text)) return false;
  return status === "done";
}

const RELEASE_STATUS_LABELS = {
  draft: "Draft",
  active: "In execution",
  completed: "Completed",
  archived: "Archived",
};

export function releaseStatusLabel(status) {
  return RELEASE_STATUS_LABELS[status] || status;
}
