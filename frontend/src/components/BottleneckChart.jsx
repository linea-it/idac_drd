import { Box, LinearProgress, Stack, Typography } from "@mui/material";

function formatDuration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export default function BottleneckChart({ rows }) {
  const max = Math.max(...rows.map((r) => r.primary_duration || r.compare_duration || 0), 1);
  return (
    <Stack spacing={1.5}>
      {rows.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No completed activities with duration yet.
        </Typography>
      )}
      {rows.map((row) => (
        <Box key={row.key}>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="body2">{row.label}</Typography>
            <Typography variant="caption" color="text.secondary">
              {formatDuration(row.primary_duration)}
              {row.compare_duration != null ? ` / ${formatDuration(row.compare_duration)}` : ""}
            </Typography>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={((row.primary_duration || 0) / max) * 100}
            sx={{ height: 8, borderRadius: 1, mt: 0.5 }}
          />
        </Box>
      ))}
    </Stack>
  );
}
