import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  FormLabel,
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

const STATUSES = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" },
  { value: "done", label: "Done" },
];

export default function ActivityDrawer({
  open,
  activity,
  releaseSlug,
  users,
  lanes,
  activities,
  readonly,
  onClose,
  onSave,
  onDelete,
  onMove,
}) {
  const [status, setStatus] = useState("todo");
  const [mode, setMode] = useState("manual");
  const [assigneeId, setAssigneeId] = useState("");
  const [notes, setNotes] = useState("");
  const [blockedReason, setBlockedReason] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [laneId, setLaneId] = useState("");
  const [dependsOnIds, setDependsOnIds] = useState([]);
  const [moveLaneId, setMoveLaneId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [transitions, setTransitions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    if (!activity || !releaseSlug) return;
    let cancelled = false;
    setHistoryLoading(true);
    api
      .get(`/api/releases/${releaseSlug}/transitions/`)
      .then((list) => {
        if (cancelled) return;
        setTransitions(list.filter((t) => t.activity === activity.id));
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
    setLabel(activity.label);
    setDescription(activity.description || "");
    setLaneId(activity.lane);
    setDependsOnIds((activity.depends_on || []).map(Number));
    setMoveLaneId(activity.lane);
    setAfterId("");
    setError("");
  }, [activity]);

  if (!activity) return null;

  const moveLaneActivities = activities.filter(
    (a) => a.id !== activity.id && (a.lane === Number(moveLaneId) || a.lane === moveLaneId),
  );
  const depOptions = activities.filter((a) => a.id !== activity.id);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await onSave({
        status,
        mode,
        assignee_id: assigneeId === "" ? null : Number(assigneeId),
        notes,
        blocked_reason: blockedReason,
        label,
        description,
        lane_id: Number(laneId),
        depends_on_ids: dependsOnIds.map(Number),
      });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleMove() {
    setError("");
    try {
      await onMove(activity, {
        lane_id: Number(moveLaneId),
        after_id: afterId ? Number(afterId) : null,
      });
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: "100%", sm: 420 } } }}>
      <Box sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{activity.label}</Typography>
          <Typography variant="body2" color="text.secondary">
            {activity.lane_label} · {activity.key}
          </Typography>
          {activity.locked && (
            <Alert severity="warning">Locked until prerequisites are done.</Alert>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          <Accordion key={activity.id} defaultExpanded disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ "& .MuiAccordionSummary-content": { my: 0.5 } }}>
              <Typography variant="overline">Progress</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <FormControl fullWidth size="small" disabled={readonly}>
                  <InputLabel>Status</InputLabel>
                  <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
                    {STATUSES.map((s) => (
                      <MenuItem key={s.value} value={s.value}>
                        {s.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
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
                        {u.username}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl disabled={readonly}>
                  <FormLabel>Mode</FormLabel>
                  <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value)}>
                    <FormControlLabel value="manual" control={<Radio size="small" />} label="Manual" />
                    <FormControlLabel value="nifi" control={<Radio size="small" />} label="NiFi" />
                  </RadioGroup>
                </FormControl>
                {status === "blocked" && (
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
                  disabled={readonly}
                />
                <TextField
                  label="Description"
                  size="small"
                  fullWidth
                  multiline
                  minRows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={readonly}
                />
                <FormControl fullWidth size="small" disabled={readonly}>
                  <InputLabel>Lane</InputLabel>
                  <Select label="Lane" value={laneId} onChange={(e) => setLaneId(e.target.value)}>
                    {lanes.map((l) => (
                      <MenuItem key={l.id} value={l.id}>
                        {l.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth size="small" disabled={readonly}>
                  <InputLabel>Depends on</InputLabel>
                  <Select
                    label="Depends on"
                    multiple
                    value={dependsOnIds}
                    onChange={(e) => setDependsOnIds(e.target.value)}
                  >
                    {depOptions.map((a) => (
                      <MenuItem key={a.id} value={a.id}>
                        {a.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Stack>
            </AccordionDetails>
          </Accordion>
          {!readonly && (
            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ "& .MuiAccordionSummary-content": { my: 0.5 } }}>
                <Typography variant="overline">Move</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>To lane</InputLabel>
                    <Select label="To lane" value={moveLaneId} onChange={(e) => setMoveLaneId(e.target.value)}>
                      {lanes.map((l) => (
                        <MenuItem key={l.id} value={l.id}>
                          {l.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel>After</InputLabel>
                    <Select label="After" value={afterId} onChange={(e) => setAfterId(e.target.value)}>
                      <MenuItem value="">(none / start of lane)</MenuItem>
                      {moveLaneActivities.map((a) => (
                        <MenuItem key={a.id} value={a.id}>
                          {a.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Button variant="outlined" onClick={handleMove}>
                    Move here
                  </Button>
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}
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
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={handleSave} disabled={readonly || saving}>
              Save
            </Button>
            <Button variant="outlined" onClick={onClose}>
              Close
            </Button>
            {!readonly && activity.status === "todo" && (
              <Button color="error" onClick={() => onDelete(activity)}>
                Delete
              </Button>
            )}
          </Stack>
        </Stack>
      </Box>
    </Drawer>
  );
}
