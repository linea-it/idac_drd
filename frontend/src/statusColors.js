export const statusColors = {
  todo: "default",
  // marcador: o Chip não tem cor "waiting"; statusChipProps pinta pelo tema
  waiting: "waiting",
  in_progress: "info",
  in_review: "secondary",
  blocked: "warning",
  done: "success",
};

export function statusChipProps(color) {
  if (color === "waiting") {
    return {
      color: "default",
      sx: { bgcolor: "waiting.main", color: "waiting.contrastText" },
    };
  }
  return { color, sx: {} };
}
