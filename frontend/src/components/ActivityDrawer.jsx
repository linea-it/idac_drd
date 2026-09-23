import AddIcon from "@mui/icons-material/Add";
import ControlPointDuplicateIcon from "@mui/icons-material/ControlPointDuplicate";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";
import { displayStatus, isPrereqAutoBlock, statusLabel } from "../activityStatus";
import {
  canControlTimer,
  formatEffort,
  timerGateMessage,
  timerGateReason,
} from "../timerUi";
import DependsOnField from "./DependsOnField";

// estados operacionais que o executor escolhe; a conclusão (done) é ação
// explícita. in_review só aparece se ainda houver linha legada.
const STATUS_OPTIONS = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" },
];
const NON_SELECTABLE = {
  in_review: "In review",
  done: "Done",
};

export default function ActivityDrawer({
  open,
  activity,
  releaseSlug,
  users,
  githubOptions = { repos: [], areas: [], sizes: [] },
  steps,
  activities,
  readonly,
  draft,
  canEdit = true,
  onClose,
  onSave,
  onDelete,
  onDuplicate,
  onMove,
  onPlay,
  onPause,
  onRecordEffort,
  isSuperuser = false,
  userEmail = "",
}) {
  const [status, setStatus] = useState("todo");
  const [mode, setMode] = useState("manual");
  const [assigneeId, setAssigneeId] = useState("");
  const [notes, setNotes] = useState("");
  const [blockedReason, setBlockedReason] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [area, setArea] = useState("");
  const [size, setSize] = useState("");
  const [stepId, setStepId] = useState("");
  const [dependsOnIds, setDependsOnIds] = useState([]);
  const [manualMinutes, setManualMinutes] = useState("");
  const [showManualEffort, setShowManualEffort] = useState(false);
  const [resources, setResources] = useState([]);
  const [moveStepId, setMoveStepId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [transitions, setTransitions] = useState([]);
  const [textRevisions, setTextRevisions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [checkedObjectives, setCheckedObjectives] = useState([]);

  useEffect(() => {
    if (!activity || !releaseSlug) return;
    let cancelled = false;
    setHistoryLoading(true);
    Promise.all([
      api.get(`/api/releases/${releaseSlug}/transitions/`),
      api.get(`/api/releases/${releaseSlug}/text-revisions/`),
    ])
      .then(([transitionsList, revisionsList]) => {
        if (cancelled) return;
        setTransitions(transitionsList.filter((t) => t.activity === activity.id));
        setTextRevisions(revisionsList.filter((r) => r.activity === activity.id));
        setHistoryLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activity, releaseSlug]);

  useEffect(() => {
    if (!activity) return;
    setStatus(activity.status);
    setMode(activity.mode || "manual");
    setAssigneeId(activity.assignee?.id || "");
    setNotes(activity.notes || "");
    setBlockedReason(activity.blocked_reason || "");
    setManualMinutes("");
    setShowManualEffort(false);
    setLabel(activity.label);
    setDescription(activity.description || "");
    // colchetes são formato de persistência (tickets): o dashboard mostra o
    // texto limpo; a marcação ([x] no texto) restaura os checkboxes
    setObjectives(
      (activity.objectives || "").split("\n").map((l) => l.replace(/^\[[x ]\]\s*/, "")).join("\n"),
    );
    const savedLines = (activity.objectives || "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    setCheckedObjectives(
      savedLines
        .map((l, i) => {
          if (l.toLowerCase().startsWith("[x]")) return i;
          if (/^\[[ ]\]/i.test(l)) return null;
          return activity.status === "done" ? i : null;
        })
        .filter((x) => x !== null),
    );
    setGithubRepo(activity.github_repo || "");
    setArea(activity.area || "");
    setSize(activity.size || "");
    setStepId(activity.step);
    setDependsOnIds((activity.depends_on || []).map(Number));
    setResources((activity.resources || []).map((r) => ({ label: r.label || "", url: r.url || "" })));
    setMoveStepId(activity.step);
    setAfterId("");
    setError("");
  }, [activity]);

  if (!activity) return null;

  // estrutura só se edita em draft ou no modo de edição da execução (canEdit)
  const structDisabled = readonly || !canEdit;
  const canTimer = canControlTimer(activity, { isSuperuser, userEmail });
  const gateMsg = timerGateMessage(timerGateReason(activity, { isSuperuser, userEmail }));
  const objectiveLines = objectives
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  function markedObjectives(lines, checked) {
    return lines
      .map((line, i) => `${checked.includes(i) ? "[x]" : "[ ]"} ${line.replace(/^\[[x ]\]\s*/i, "")}`)
      .join("\n");
  }

  async function toggleObjective(i) {
    const next = checkedObjectives.includes(i)
      ? checkedObjectives.filter((x) => x !== i)
      : [...checkedObjectives, i];
    setCheckedObjectives(next);
    const live = activity.status === "in_progress" || activity.status === "in_review";
    if (readonly || draft || !live) return;
    setError("");
    try {
      await onSave({
        ...buildPayload(activity.status),
        objectives: markedObjectives(objectiveLines, next),
      });
    } catch (err) {
      setCheckedObjectives(checkedObjectives);
      setError(err.message);
    }
  }

  function updateResource(i, patch) {
    setResources((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }
  function removeResource(i) {
    setResources((prev) => prev.filter((_, j) => j !== i));
  }
  function addResource() {
    setResources((prev) => [...prev, { label: "", url: "" }]);
  }
  const moveStepActivities = activities.filter(
    (a) => a.id !== activity.id && (a.step === Number(moveStepId) || a.step === moveStepId),
  );
  const depOptions = activities.filter((a) => a.id !== activity.id);

  function buildPayload(statusOverride) {
    const payload = {
      status: statusOverride || status,
      assignee_id: assigneeId === "" ? null : Number(assigneeId),
      notes,
      blocked_reason: blockedReason,
    };
    // objetivos são lista de seleção do fluxo de execução: a marcação persiste
    // mesmo sem o modo de edição estrutural (canEdit)
    payload.objectives = markedObjectives(objectiveLines, checkedObjectives);
    if (canEdit) {
      Object.assign(payload, {
        mode,
        label,
        description,
        step_id: Number(stepId),
        depends_on_ids: dependsOnIds.map(Number),
        github_repo: githubRepo,
        area,
        size,
        resources: resources
          .filter((r) => r.url.trim())
          .map((r) => ({ label: r.label.trim(), url: r.url.trim() })),
      });
    }
    return payload;
  }

  async function handleSave(statusOverride) {
    const nextStatus = typeof statusOverride === "string" ? statusOverride : undefined;
    setSaving(true);
    setError("");
    try {
      await onSave(buildPayload(nextStatus));
    } catch (err) {
      if (nextStatus) setStatus(activity.status);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  // ações de aprovação: done (aprovar) ou in_progress (rejeitar, com motivo)
  async function handleTransition(toStatus, comment = "") {
    setSaving(true);
    setError("");
    try {
      await onSave({ ...buildPayload(toStatus), comment });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function submitManualEffort() {
    if (!manualMinutes || Number(manualMinutes) <= 0) return;
    setError("");
    setSaving(true);
    try {
      await onRecordEffort(activity, Number(manualMinutes));
      setManualMinutes("");
      setShowManualEffort(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleMove() {
    setSaving(true);
    setError("");
    try {
      await onMove(activity, {
        step_id: Number(moveStepId),
        after_id: afterId ? Number(afterId) : null,
      });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: "100%", sm: 420 } } }}>
      <Box sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{activity.label}</Typography>
          <Typography variant="body2" color="text.secondary">
            {activity.step_label} · {activity.key}
          </Typography>
          {displayStatus(activity) === "waiting" && (
            <Alert severity="info">Finish the prerequisites to unlock this activity.</Alert>
          )}
          {displayStatus(activity) === "blocked" && (
            <Alert severity="warning">
              {activity.blocked_reason
                ? `This activity is blocked: ${activity.blocked_reason}`
                : "This activity is blocked."}
            </Alert>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          <Accordion key={activity.id} defaultExpanded disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ "& .MuiAccordionSummary-content": { my: 0.5 } }}>
              <Typography variant="overline">Progress</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                {/* transições só existem em execução: em draft o status não muda */}
                <FormControl fullWidth size="small" disabled={readonly || draft}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    label="Status"
                    value={status}
                    onChange={(e) => {
                      const next = e.target.value;
                      setStatus(next);
                      handleSave(next);
                    }}
                    renderValue={(v) =>
                      displayStatus(activity) === "waiting" && v === "blocked"
                        ? statusLabel("waiting")
                        : STATUS_OPTIONS.find((s) => s.value === v)?.label ||
                          NON_SELECTABLE[v] ||
                          v
                    }
                  >
                    {STATUS_OPTIONS.map((s) => (
                      <MenuItem key={s.value} value={s.value}>
                        {s.label}
                      </MenuItem>
                    ))}
                    {/* in_review/done não se escolhem: são resultado das ações */}
                    {NON_SELECTABLE[status] && (
                      <MenuItem value={status} disabled>
                        {NON_SELECTABLE[status]}
                      </MenuItem>
                    )}
                  </Select>
                </FormControl>
                {!readonly &&
                  !draft &&
                  canTimer &&
                  (status === "todo" || status === "in_progress") &&
                  (activity.prerequisites_met !== false || activity.status === "in_progress") &&
                  displayStatus(activity) !== "waiting" && (
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ width: "100%" }}>
                      {activity.is_playing ? (
                        <Button
                          variant="outlined"
                          startIcon={<PauseIcon />}
                          onClick={async () => {
                            setError("");
                            setSaving(true);
                            try {
                              await onPause?.(activity);
                            } catch (err) {
                              setError(err.message);
                            } finally {
                              setSaving(false);
                            }
                          }}
                          disabled={saving || !onPause}
                        >
                          Pause
                        </Button>
                      ) : (
                        <Button
                          variant="contained"
                          startIcon={<PlayArrowIcon />}
                          onClick={async () => {
                            setError("");
                            setSaving(true);
                            try {
                              await onPlay?.(activity);
                            } catch (err) {
                              setError(err.message);
                            } finally {
                              setSaving(false);
                            }
                          }}
                          disabled={
                            saving ||
                            !onPlay ||
                            !activity.assignee ||
                            activity.prerequisites_met === false
                          }
                        >
                          Play
                        </Button>
                      )}
                      {activity.effort_seconds > 0 && formatEffort(activity.effort_seconds) ? (
                        <Typography variant="body2" color="text.secondary">
                          {activity.is_playing ? "In Progress · " : "Effort · "}
                          {formatEffort(activity.effort_seconds)}
                        </Typography>
                      ) : (
                        showManualEffort &&
                        status === "in_progress" &&
                        activity.status === "in_progress" &&
                        !activity.is_playing &&
                        onRecordEffort && (
                          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ ml: "auto" }}>
                            <TextField
                              size="small"
                              type="number"
                              label="Minutes"
                              value={manualMinutes}
                              onChange={(e) => setManualMinutes(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Escape") {
                                  setShowManualEffort(false);
                                  setManualMinutes("");
                                  return;
                                }
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  submitManualEffort();
                                }
                              }}
                              inputProps={{ min: 1, step: 1, max: 24 * 60 }}
                              sx={{ width: 120 }}
                              autoFocus
                            />
                            <Button
                              size="small"
                              variant="text"
                              disabled={saving || !manualMinutes || Number(manualMinutes) <= 0}
                              aria-label="Save effort"
                              onClick={submitManualEffort}
                              sx={{ textTransform: "none", minWidth: 0 }}
                            >
                              Save
                            </Button>
                            <Button
                              size="small"
                              variant="text"
                              color="inherit"
                              disabled={saving}
                              aria-label="Cancel effort"
                              onClick={() => {
                                setShowManualEffort(false);
                                setManualMinutes("");
                              }}
                              sx={{ color: "text.secondary", textTransform: "none", minWidth: 0, px: 0.5 }}
                            >
                              Cancel
                            </Button>
                          </Stack>
                        )
                      )}
                      {!showManualEffort &&
                        status === "in_progress" &&
                        activity.status === "in_progress" &&
                        !activity.is_playing &&
                        !(activity.effort_seconds > 0) &&
                        onRecordEffort && (
                          <Button
                            size="small"
                            variant="text"
                            color="inherit"
                            sx={{
                              ml: "auto",
                              color: "text.secondary",
                              textTransform: "none",
                              fontWeight: 400,
                              minWidth: 0,
                              px: 0.5,
                            }}
                            disabled={saving}
                            onClick={() => setShowManualEffort(true)}
                          >
                            Add Effort
                          </Button>
                        )}
                    </Stack>
                  )}
                {!readonly &&
                  !draft &&
                  !canTimer &&
                  (status === "todo" || status === "in_progress") &&
                  displayStatus(activity) !== "waiting" && (
                    <Stack spacing={0.5}>
                      {gateMsg && (
                        <Typography variant="caption" color="text.secondary">
                          {gateMsg}
                        </Typography>
                      )}
                      {formatEffort(activity.effort_seconds) && (
                        <Typography variant="body2" color="text.secondary">
                          {activity.is_playing ? "In Progress · " : "Effort · "}
                          {formatEffort(activity.effort_seconds)}
                        </Typography>
                      )}
                    </Stack>
                  )}
                {activity.status === "done" && objectiveLines.length > 0 && (
                  <Box>
                    <Typography variant="overline">Objectives</Typography>
                    {objectiveLines.map((line, i) => (
                      <Box key={i} sx={{ display: "flex", alignItems: "flex-start" }}>
                        <Checkbox
                          size="small"
                          checked={checkedObjectives.includes(i)}
                          disabled
                          inputProps={{ "aria-label": line }}
                          sx={{ padding: 0, mr: 1.5, mt: "2px" }}
                        />
                        <Typography variant="body2" sx={{ flex: 1, pt: "2px" }}>
                          {line}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                )}
                {!readonly &&
                  !draft &&
                  (activity.status === "in_progress" || activity.status === "in_review") &&
                  status === activity.status && (
                  <Stack spacing={0.5}>
                    {objectiveLines.length > 0 && (
                      <Box>
                        <Typography variant="overline">
                          Objectives · {checkedObjectives.length}/{objectiveLines.length}
                        </Typography>
                        {objectiveLines.map((line, i) => (
                          <Box key={i} sx={{ display: "flex", alignItems: "flex-start" }}>
                            <Checkbox
                              size="small"
                              checked={checkedObjectives.includes(i)}
                              onChange={() => toggleObjective(i)}
                              inputProps={{ "aria-label": line }}
                              sx={{ padding: 0, mr: 1.5, mt: "2px" }}
                            />
                            <Typography variant="body2" sx={{ flex: 1, pt: "2px" }}>
                              {line}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    )}
                    <Button
                      variant="contained"
                      color="success"
                      onClick={() => handleTransition("done")}
                      disabled={
                        saving ||
                        !(activity.is_playing || (activity.effort_seconds ?? 0) > 0) ||
                        (objectiveLines.length > 0 && checkedObjectives.length < objectiveLines.length)
                      }
                    >
                      Complete
                    </Button>
                    {!(activity.is_playing || (activity.effort_seconds ?? 0) > 0) && (
                      <Typography variant="caption" color="text.secondary">
                        No effort yet — use Play or Add Effort first
                      </Typography>
                    )}
                    {objectiveLines.length > 0 && checkedObjectives.length < objectiveLines.length && (
                      <Typography variant="caption" color="text.secondary">
                        Check every objective to complete
                      </Typography>
                    )}
                  </Stack>
                )}
                <FormControl fullWidth size="small" disabled={readonly}>
                  <InputLabel>Assignee</InputLabel>
                  <Select
                    label="Assignee"
                    value={assigneeId}
                    onChange={(e) => setAssigneeId(e.target.value)}
                  >
                    <MenuItem value="">Unassigned</MenuItem>
                    {users.map((u) => (
                      <MenuItem key={u.id} value={u.id}>
                        {u.name || u.email}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl disabled={structDisabled}>
                  <FormLabel>Mode</FormLabel>
                  <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value)}>
                    <FormControlLabel value="manual" control={<Radio size="small" />} label="Manual" />
                    <FormControlLabel value="nifi" control={<Radio size="small" />} label="NiFi" />
                  </RadioGroup>
                </FormControl>
                {status === "blocked" && !isPrereqAutoBlock(activity) && (
                  <TextField
                    label="Blocked reason"
                    size="small"
                    fullWidth
                    multiline
                    minRows={2}
                    value={blockedReason}
                    onChange={(e) => setBlockedReason(e.target.value)}
                    disabled={readonly}
                  />
                )}
                {displayStatus(activity) === "waiting" && activity.blocked_reason && (
                  <Typography variant="body2" color="text.secondary">
                    {activity.blocked_reason}
                  </Typography>
                )}
                <TextField
                  label="Notes"
                  size="small"
                  fullWidth
                  multiline
                  minRows={3}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  disabled={readonly}
                />
              </Stack>
            </AccordionDetails>
          </Accordion>
          <Accordion disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ "& .MuiAccordionSummary-content": { my: 0.5 } }}>
              <Typography variant="overline">Details</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <TextField
                  label="Label"
                  size="small"
                  fullWidth
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  disabled={structDisabled}
                />
                <Autocomplete
                  freeSolo
                  size="small"
                  fullWidth
                  options={githubOptions.repos || []}
                  value={githubRepo}
                  onInputChange={(_, v) => setGithubRepo(v)}
                  disabled={structDisabled}
                  renderInput={(params) => <TextField {...params} label="GitHub repo" size="small" />}
                />
                <Autocomplete
                  freeSolo
                  size="small"
                  fullWidth
                  options={githubOptions.areas || []}
                  value={area}
                  onInputChange={(_, v) => setArea(v)}
                  disabled={structDisabled}
                  renderInput={(params) => <TextField {...params} label="Area" size="small" />}
                />
                <Autocomplete
                  freeSolo
                  size="small"
                  fullWidth
                  options={githubOptions.sizes || []}
                  value={size}
                  onInputChange={(_, v) => setSize(v)}
                  disabled={structDisabled}
                  renderInput={(params) => <TextField {...params} label="Size" size="small" />}
                />
                <TextField
                  label="Description"
                  size="small"
                  fullWidth
                  multiline
                  minRows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={structDisabled}
                />
                <TextField
                  label="Objectives"
                  size="small"
                  fullWidth
                  multiline
                  minRows={2}
                  helperText="One objective per line"
                  value={objectives}
                  onChange={(e) => setObjectives(e.target.value)}
                  disabled={structDisabled}
                />
                <Box>
                  <Typography variant="overline">Resources</Typography>
                  {resources.map((r, i) => (
                    <Stack key={i} direction="row" spacing={1} sx={{ mb: 1, alignItems: "flex-start" }}>
                      <TextField
                        size="small"
                        label="Label"
                        value={r.label}
                        onChange={(e) => updateResource(i, { label: e.target.value })}
                        disabled={structDisabled}
                        sx={{ flex: 1 }}
                      />
                      <TextField
                        size="small"
                        label="URL"
                        placeholder="https://docs.google.com/…"
                        value={r.url}
                        onChange={(e) => updateResource(i, { url: e.target.value })}
                        disabled={structDisabled}
                        sx={{ flex: 2 }}
                      />
                      <IconButton size="small" onClick={() => removeResource(i)} disabled={structDisabled} title="Remove resource">
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  ))}
                  <Button
                    size="small"
                    startIcon={<AddIcon />}
                    onClick={addResource}
                    disabled={structDisabled}
                  >
                    Add resource
                  </Button>
                </Box>
                <FormControl fullWidth size="small" disabled={structDisabled}>
                  <InputLabel>Step</InputLabel>
                  <Select label="Step" value={stepId} onChange={(e) => setStepId(e.target.value)}>
                    {steps.map((l) => (
                      <MenuItem key={l.id} value={l.id}>
                        {l.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <DependsOnField
                  activities={depOptions}
                  value={dependsOnIds}
                  onChange={setDependsOnIds}
                  disabled={structDisabled}
                />
              </Stack>
            </AccordionDetails>
          </Accordion>
          {!readonly && canEdit && (
            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ "& .MuiAccordionSummary-content": { my: 0.5 } }}>
                <Typography variant="overline">Move</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>To step</InputLabel>
                    <Select label="To step" value={moveStepId} onChange={(e) => setMoveStepId(e.target.value)}>
                      {steps.map((l) => (
                        <MenuItem key={l.id} value={l.id}>
                          {l.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel>After</InputLabel>
                    <Select label="After" value={afterId} onChange={(e) => setAfterId(e.target.value)}>
                      <MenuItem value="">(none / start of step)</MenuItem>
                      {moveStepActivities.map((a) => (
                        <MenuItem key={a.id} value={a.id}>
                          {a.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Button variant="outlined" onClick={handleMove} disabled={saving}>
                    Move here
                  </Button>
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={() => handleSave()} disabled={readonly || saving}>
              Save
            </Button>
            <Button variant="outlined" onClick={onClose}>
              Close
            </Button>
          </Stack>
          <Divider />
          <Typography variant="overline">History</Typography>
          {historyLoading ? (
            <LinearProgress />
          ) : transitions.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No transitions yet.
            </Typography>
          ) : (
            transitions.map((t) => (
              <Box key={t.id}>
                <Stack direction="row" justifyContent="space-between" spacing={1}>
                  <Typography variant="body2">
                    {t.from_status} → {t.to_status}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t.actor?.username || "unknown"} · {new Date(t.created_at).toLocaleString()}
                  </Typography>
                </Stack>
                {t.comment && (
                  <Typography variant="body2" color="text.secondary">
                    {t.comment}
                  </Typography>
                )}
              </Box>
            ))
          )}
          <Divider />
          <Typography variant="overline">Text revisions</Typography>
          {historyLoading ? (
            <LinearProgress />
          ) : textRevisions.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No text revisions yet.
            </Typography>
          ) : (
            textRevisions.map((r) => (
              <Box key={r.id}>
                <Stack direction="row" justifyContent="space-between" spacing={1}>
                  <Typography variant="body2">
                    {r.field.charAt(0).toUpperCase() + r.field.slice(1)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {r.actor?.username || "unknown"} · {new Date(r.created_at).toLocaleString()}
                  </Typography>
                </Stack>
                {r.text_before && (
                  <Typography variant="body2" color="text.secondary">
                    − {r.text_before}
                  </Typography>
                )}
                {r.text_after ? (
                  <Typography variant="body2">+ {r.text_after}</Typography>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    apagou
                  </Typography>
                )}
                {!r.text_before && r.text_after && (
                  <Typography variant="caption" color="text.secondary">
                    adicionou
                  </Typography>
                )}
              </Box>
            ))
          )}
          {canEdit && (onDuplicate || draft || activity.status === "todo") ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {canEdit && onDuplicate && (
                <Button
                  variant="outlined"
                  startIcon={<ControlPointDuplicateIcon />}
                  onClick={() => onDuplicate(activity)}
                  disabled={saving}
                >
                  Make a copy
                </Button>
              )}
              {canEdit && (draft || activity.status === "todo") && (
                <Button color="error" onClick={() => onDelete(activity)}>
                  Delete
                </Button>
              )}
            </Stack>
          ) : null}
        </Stack>
      </Box>
    </Drawer>
  );
}
