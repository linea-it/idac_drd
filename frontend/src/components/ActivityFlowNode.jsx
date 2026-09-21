import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Handle, Position } from "@xyflow/react";
import { Box, Chip, IconButton, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { displayStatus, isStuck, statusLabel } from "../activityStatus";
import { statusColors } from "../statusColors";
import { canControlTimer, workflowChip } from "../timerUi";
import ModeChip from "./ModeChip";
import ResourceLinks from "./ResourceLinks";

function timerEligible(activity) {
  const status = activity.status;
  if (status !== "todo" && status !== "in_progress") return false;
  if (displayStatus(activity) === "waiting") return false;
  if (status === "todo" && activity.prerequisites_met === false) return false;
  return true;
}

export default function ActivityFlowNode({ data }) {
  const theme = useTheme();
  const {
    activity,
    level,
    revealed,
    dim,
    flash,
    onPlay,
    onPause,
    isSuperuser = false,
    userEmail = "",
  } = data;
  const stuck = isStuck(activity);
  const status = displayStatus(activity);
  const auth = { isSuperuser, userEmail };
  const showTimer =
    timerEligible(activity) && canControlTimer(activity, auth) && (onPlay || onPause);
  const chip = workflowChip(activity, displayStatus, statusLabel, statusColors);

  const borderColor =
    status === "blocked"
      ? "warning.main"
      : status === "waiting"
        ? "divider"
        : activity.status === "todo" && activity.prerequisites_met
          ? "primary.main"
          : "divider";
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

  // mesmo slot do cadeado: stuck > botão play/pause > ícone só leitura
  let statusIcon = null;
  if (stuck) {
    statusIcon = (
      <LockOutlinedIcon
        sx={{ fontSize: "0.875rem", color: "text.primary", flexShrink: 0 }}
        titleAccess="Stuck"
      />
    );
  } else if (showTimer) {
    statusIcon = (
      <IconButton
        size="small"
        color={activity.is_playing ? "success" : "primary"}
        title={activity.is_playing ? "Pause" : "Play"}
        aria-label={activity.is_playing ? "Pause" : "Play"}
        onClick={(e) => {
          e.stopPropagation();
          if (activity.is_playing) onPause?.(activity);
          else onPlay?.(activity);
        }}
        sx={{ p: 0.25 }}
      >
        {activity.is_playing ? (
          <PauseIcon sx={{ fontSize: "0.875rem" }} />
        ) : (
          <PlayArrowIcon sx={{ fontSize: "0.875rem" }} />
        )}
      </IconButton>
    );
  } else if (activity.is_playing) {
    statusIcon = (
      <PlayArrowIcon
        sx={{ fontSize: "0.875rem", color: "success.main", flexShrink: 0 }}
        titleAccess="In Progress"
      />
    );
  } else if (activity.status === "in_progress") {
    statusIcon = (
      <PauseIcon
        sx={{ fontSize: "0.875rem", color: "text.secondary", flexShrink: 0 }}
        titleAccess="Paused"
      />
    );
  }

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
            borderLeft: `4px solid ${data.stepColor || "#000099"}`,
            boxShadow: flash ? `0 0 0 3px ${flashColor}` : "none",
            px: 1.5,
            py: 1,
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
            {statusIcon}
            <ResourceLinks resources={activity.resources} sx={{ p: 0.25 }} />
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center">
            <Chip
              size="small"
              label={chip.label}
              color={chip.color}
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
