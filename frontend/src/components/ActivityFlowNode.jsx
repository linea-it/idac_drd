import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import { Handle, Position } from "@xyflow/react";
import { Box, Chip, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { displayStatus, isStuck, statusLabel } from "../activityStatus";
import { statusColors } from "../statusColors";
import ModeChip from "./ModeChip";
import ResourceLinks from "./ResourceLinks";

export default function ActivityFlowNode({ data }) {
  const theme = useTheme();
  const { activity, level, revealed, dim, flash } = data;
  const stuck = isStuck(activity);
  const status = displayStatus(activity);
  const borderColor =
    status === "blocked"
      ? "warning.main"
      : status === "waiting"
        ? "divider"
        : activity.status === "todo" && activity.prerequisites_met
          ? "primary.main"
          : "divider";
  // cor do anel de "recém-editado": a cor do status efetivo atual
  const flashColor =
    status === "blocked"
      ? theme.palette.warning.main
      : status === "waiting"
        ? theme.palette.text.disabled
        : status === "in_progress"
          ? theme.palette.info.main
          : status === "done"
            ? theme.palette.success.main
            : theme.palette.primary.main;

  return (
    <>
      <Handle type="target" position={Position.Left} />
      <Box sx={{ opacity: revealed ? 1 : 0, transition: `opacity 400ms ease ${(level || 0) * 80}ms` }}>
        <Box
          sx={{
            width: 250,
            bgcolor: "background.paper",
            border: 1,
            borderColor,
            borderRadius: 1,
            // a faixa desse step a que a activity pertence (mesma cor do rótulo da faixa)
            borderLeft: `4px solid ${data.stepColor || "#000099"}`,
            boxShadow: flash ? `0 0 0 3px ${flashColor}` : "none",
            px: 1.5,
            py: 1,
            // só filtro/hover esmaece — waiting/blocked ficam opacos
            opacity: dim ? 0.35 : 1,
            transition: "opacity 150ms ease, border-color 300ms ease, box-shadow 600ms ease",
          }}
        >
        <Stack spacing={0.5}>
          <Stack direction="row" alignItems="center" spacing={0.5} sx={{ minWidth: 0 }}>
            <Typography
              variant="body2"
              fontWeight={600}
              sx={{
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {activity.label}
            </Typography>
            {stuck && (
              <LockOutlinedIcon
                sx={{ fontSize: "0.875rem", color: "text.primary", flexShrink: 0 }}
                titleAccess="Stuck"
              />
            )}
            <ResourceLinks resources={activity.resources} sx={{ p: 0.25 }} />
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center">
            <Chip
              size="small"
              label={statusLabel(status)}
              color={statusColors[status]}
              sx={{ height: 20, "& .MuiChip-label": { fontSize: 11, px: 0.8 } }}
            />
            <ModeChip mode={activity.mode} size="small" sx={{ height: 20 }} />
            {activity.assignee && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {activity.assignee.name || activity.assignee.email}
              </Typography>
            )}
          </Stack>
        </Stack>
        </Box>
      </Box>
      <Handle type="source" position={Position.Right} />
    </>
  );
}
