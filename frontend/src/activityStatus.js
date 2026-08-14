// Status efetivo para exibição: atividade em "todo" com pré-requisito ainda não
// resolvido é exibida como "blocked" (não pode começar). O status real no banco
// permanece "todo" — o bloqueio é derivado de depends_on via prerequisites_met.
export function displayStatus(activity) {
  return activity.status === "todo" && !activity.prerequisites_met
    ? "blocked"
    : activity.status;
}

// Rótulos humanizados dos chips de status (sem underscore, capitalizados).
const STATUS_LABELS = {
  todo: "Waiting",
  in_progress: "In Progress",
  done: "Completed",
  blocked: "Blocked",
};

export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

const RELEASE_STATUS_LABELS = {
  planned: "Planned",
  active: "Active",
  completed: "Completed",
  archived: "Archived",
};

export function releaseStatusLabel(status) {
  return RELEASE_STATUS_LABELS[status] || status;
}
