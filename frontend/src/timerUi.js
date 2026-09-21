/** Helpers de play/pause / effort na UI. */

export function formatEffort(seconds) {
  if (seconds == null || seconds < 0) return null;
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

/** Assignee (email) ou superuser. */
export function canControlTimer(activity, { isSuperuser = false, userEmail = "" } = {}) {
  if (!activity?.assignee) return false;
  if (isSuperuser) return true;
  const mine = (userEmail || "").trim().toLowerCase();
  const theirs = (activity.assignee.email || "").trim().toLowerCase();
  return Boolean(mine && theirs && mine === theirs);
}

/**
 * Por que o botão some / está bloqueado (quando o status permitiria timer).
 * null = pode controlar.
 */
export function timerGateReason(activity, { isSuperuser = false, userEmail = "" } = {}) {
  if (!activity?.assignee) return "no_assignee";
  if (isSuperuser) return null;
  const mine = (userEmail || "").trim().toLowerCase();
  const theirs = (activity.assignee.email || "").trim().toLowerCase();
  if (!mine) return "no_login_email";
  if (mine !== theirs) return "email_mismatch";
  return null;
}

export function timerGateMessage(reason) {
  switch (reason) {
    case "no_assignee":
      return "Assign someone to play";
    case "no_login_email":
      return "Your login has no email — can't match the assignee";
    case "email_mismatch":
      return "Only the assignee (or a superuser) can play/pause";
    default:
      return null;
  }
}

/** Chip de workflow: In Progress (timer ligado) / Paused (in_progress sem sessão). */
export function workflowChip(activity, displayStatusFn, statusLabelFn, statusColorsMap) {
  if (activity.status === "in_progress") {
    if (activity.is_playing) {
      return { label: "In Progress", color: "info" };
    }
    return { label: "Paused", color: "default" };
  }
  const s = displayStatusFn(activity);
  return { label: statusLabelFn(s), color: statusColorsMap[s] };
}
