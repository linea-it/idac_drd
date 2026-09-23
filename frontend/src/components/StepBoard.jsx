import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ControlPointDuplicateIcon from "@mui/icons-material/ControlPointDuplicate";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Box, Card, CardActionArea, CardContent, Chip, IconButton, Stack, Typography } from "@mui/material";
import { displayStatus, isObjectiveChecked, objectiveItems, statusLabel } from "../activityStatus";
import { statusColors } from "../statusColors";
import {
  canControlTimer,
  timerGateMessage,
  timerGateReason,
  workflowChip,
} from "../timerUi";
import ModeChip from "./ModeChip";
import ResourceLinks from "./ResourceLinks";

function timerEligible(activity) {
  const status = activity.status;
  if (status !== "todo" && status !== "in_progress") return false;
  if (displayStatus(activity) === "waiting") return false;
  if (status === "todo" && activity.prerequisites_met === false) return false;
  return true;
}

export default function StepBoard({
  steps,
  activities,
  onSelect,
  editable = false,
  onEditStep,
  onDeleteStep,
  onReorderStep,
  onMoveActivity,
  onDuplicateActivity,
  onPlay,
  onPause,
  isSuperuser = false,
  userEmail = "",
  matchedIds = null,
  filterActive = false,
  hideUnmatched = false,
}) {
  const firstStep = steps[0];
  const lastStep = steps[steps.length - 1];
  const auth = { isSuperuser, userEmail };
  return (
    <Box
      sx={{
        display: "flex",
        gap: 2,
        overflowX: "auto",
        pb: 2,
        alignItems: "flex-start",
      }}
    >
      {steps.map((step) => {
        const stepActs = activities
          .filter((a) => a.step === step.id)
          .sort((a, b) => a.order - b.order);
        const visibleActs =
          hideUnmatched && filterActive
            ? stepActs.filter((a) => matchedIds?.has(a.id))
            : stepActs;
        if (hideUnmatched && filterActive && visibleActs.length === 0) return null;
        return (
          <Box key={step.id} sx={{ minWidth: 260, maxWidth: 280, flex: "0 0 auto" }}>
            <Box
              sx={{
                bgcolor: step.color || "#0989cb",
                color: "#fff",
                px: 1.5,
                py: 1,
                borderRadius: 1,
                mb: 1,
              }}
            >
            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  {step.label}
                </Typography>
                <Typography variant="caption">
                  {stepActs.filter((a) => a.status === "done").length}/{stepActs.length} done
                </Typography>
              </Box>
              <Stack direction="row" alignItems="center">
                <ResourceLinks
                  resources={step.resources}
                  sx={{ color: "rgba(255,255,255,0.85)" }}
                />
                {editable && (
                <Stack direction="row">
                  <IconButton
                    size="small"
                    sx={{ color: "rgba(255,255,255,0.85)" }}
                    title="Move step left"
                    disabled={step.id === firstStep?.id}
                    onClick={() => onReorderStep(step, -1)}
                  >
                    <ArrowBackIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    sx={{ color: "rgba(255,255,255,0.85)" }}
                    title="Move step right"
                    disabled={step.id === lastStep?.id}
                    onClick={() => onReorderStep(step, 1)}
                  >
                    <ArrowForwardIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    sx={{ color: "rgba(255,255,255,0.85)" }}
                    title="Edit step"
                    onClick={() => onEditStep(step)}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    sx={{ color: "rgba(255,255,255,0.85)" }}
                    title="Delete step"
                    onClick={() => onDeleteStep(step)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              )}
              </Stack>
            </Stack>
            </Box>
            <Stack spacing={1}>
              {visibleActs.map((activity, actIdx) => {
                const eligible = timerEligible(activity);
                const playBlocked = activity.status === "in_progress" && activity.prerequisites_met === false && !activity.is_playing;
                const showTimer = eligible && canControlTimer(activity, auth) && (onPlay || onPause);
                const gateReason =
                  eligible && (onPlay || onPause) && !canControlTimer(activity, auth)
                    ? timerGateReason(activity, auth)
                    : null;
                const gateMsg =
                  gateReason && gateReason !== "email_mismatch"
                    ? timerGateMessage(gateReason)
                    : null;
                const chip = workflowChip(activity, displayStatus, statusLabel, statusColors);
                return (
                <Card
                  key={activity.id}
                  variant="outlined"
                  sx={{
                    opacity: filterActive && !matchedIds?.has(activity.id) ? 0.35 : 1,
                    borderColor:
                      displayStatus(activity) === "blocked" ? "warning.main" : "divider",
                  }}
                >
                  <CardActionArea onClick={() => onSelect(activity)}>
                    <CardContent sx={{ py: 1.5, pb: 1, "&:last-child": { pb: 1 } }}>
                      <Stack spacing={1}>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <Typography
                            variant="body2"
                            fontWeight={600}
                            sx={{ flex: 1, minWidth: 0 }}
                          >
                            {activity.label}
                          </Typography>
                          <ResourceLinks
                            resources={activity.resources}
                            sx={{ p: 0.25, ml: "auto" }}
                          />
                          {editable && (
                            <Stack direction="row">
                              <IconButton
                                size="small"
                                title="Make a copy"
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDuplicateActivity(activity);
                                }}
                              >
                                <ControlPointDuplicateIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                title="Move activity up"
                                disabled={actIdx === 0}
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onMoveActivity(activity, -1);
                                }}
                              >
                                <ArrowUpwardIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                title="Move activity down"
                                disabled={actIdx === visibleActs.length - 1}
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onMoveActivity(activity, 1);
                                }}
                              >
                                <ArrowDownwardIcon fontSize="small" />
                              </IconButton>
                            </Stack>
                          )}
                          <ModeChip mode={activity.mode} iconOnly />
                        </Stack>
                        {objectiveItems(activity.objectives).length > 0 && (
                          <>
                            {activity.status !== "done" && (
                              <Typography variant="caption" color="text.secondary">
                                {objectiveItems(activity.objectives).filter((obj) => isObjectiveChecked(obj, activity.status)).length}
                                /{objectiveItems(activity.objectives).length}
                              </Typography>
                            )}
                            {objectiveItems(activity.objectives).map((obj, i) => (
                              <Typography key={i} variant="caption" color="text.secondary">
                                {isObjectiveChecked(obj, activity.status) ? "✓ " : "○ "}
                                {obj.replace(/^\[[x ]\]\s*/, "")}
                              </Typography>
                            ))}
                          </>
                        )}
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                  <Stack
                    direction="row"
                    spacing={0.5}
                    alignItems="flex-start"
                    sx={{ px: 1.5, pb: gateMsg ? 0.5 : 1.5 }}
                  >
                    <Stack
                      direction="row"
                      spacing={0.5}
                      flexWrap="wrap"
                      useFlexGap
                      alignItems="center"
                      sx={{ flex: 1, minWidth: 0 }}
                    >
                      <Chip size="small" label={chip.label} color={chip.color} />
                      {activity.assignee && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={activity.assignee.name || activity.assignee.email}
                        />
                      )}
                    </Stack>
                    {showTimer && (
                      <IconButton
                        size="small"
                        color={activity.is_playing ? "success" : "primary"}
                        title={playBlocked ? "Finish the prerequisites first" : activity.is_playing ? "Pause" : "Play"}
                        aria-label={activity.is_playing ? "Pause" : "Play"}
                        disabled={playBlocked}
                        sx={{
                          flexShrink: 0,
                          width: 24,
                          height: 24,
                          p: 0,
                          border: 1,
                          borderRadius: 1,
                          borderColor: playBlocked
                            ? "action.disabled"
                            : activity.is_playing
                              ? "success.main"
                              : "primary.main",
                        }}
                        onClick={() => {
                          if (playBlocked) return;
                          if (activity.is_playing) onPause?.(activity);
                          else onPlay?.(activity);
                        }}
                      >
                        {activity.is_playing ? (
                          <PauseIcon sx={{ fontSize: 16 }} />
                        ) : (
                          <PlayArrowIcon sx={{ fontSize: 16 }} />
                        )}
                      </IconButton>
                    )}
                  </Stack>
                  {gateMsg && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: "block", px: 1.5, pb: 1.5 }}
                    >
                      {gateMsg}
                    </Typography>
                  )}
                </Card>
                );
              })}
            </Stack>
          </Box>
        );
      })}
    </Box>
  );
}
