import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ControlPointDuplicateIcon from "@mui/icons-material/ControlPointDuplicate";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import LockIcon from "@mui/icons-material/Lock";
import { Box, Card, CardActionArea, CardContent, Chip, IconButton, Stack, Typography } from "@mui/material";
import { displayStatus, statusLabel } from "../activityStatus";
import { statusColors } from "../statusColors";
import ResourceLinks from "./ResourceLinks";

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
}) {
  const firstStep = steps[0];
  const lastStep = steps[steps.length - 1];
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
              {stepActs.map((activity, actIdx) => (
                <Card
                  key={activity.id}
                  variant="outlined"
                  sx={{
                    opacity: activity.locked ? 0.7 : 1,
                    borderColor:
                      displayStatus(activity) === "blocked" ? "warning.main" : "divider",
                  }}
                >
                  <CardActionArea onClick={() => onSelect(activity)}>
                    <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                      <Stack spacing={1}>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          {activity.locked && <LockIcon fontSize="small" color="disabled" />}
                          <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>
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
                                disabled={actIdx === stepActs.length - 1}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onMoveActivity(activity, 1);
                                }}
                              >
                                <ArrowDownwardIcon fontSize="small" />
                              </IconButton>
                            </Stack>
                          )}
                        </Stack>
                        {activity.objectives &&
                          activity.objectives
                            .split("\n")
                            .map((s) => s.trim())
                            .filter(Boolean)
                            .map((obj, i) => (
                              <Typography key={i} variant="caption" color="text.secondary">
                                {activity.status === "done" ? "✓ " : "○ "}
                                {/* o prefixo [x]/[ ] é de persistência (tickets); o card mostra só o texto */}
                                {obj.replace(/^\[[x ]\]\s*/, "")}
                              </Typography>
                            ))}
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          <Chip
                            size="small"
                            label={statusLabel(displayStatus(activity))}
                            color={statusColors[displayStatus(activity)]}
                          />
                          <Chip
                            size="small"
                            label={activity.mode === "nifi" ? "NiFi" : "Manual"}
                            color={activity.mode === "nifi" ? "info" : "default"}
                          />
                          {activity.assignee && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={activity.assignee.name || activity.assignee.email}
                            />
                          )}
                        </Stack>
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
          </Box>
        );
      })}
    </Box>
  );
}
