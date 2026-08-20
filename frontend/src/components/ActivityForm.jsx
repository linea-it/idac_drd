import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import {
  Autocomplete,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import DependsOnField from "./DependsOnField";

const EMPTY_OPTIONS = { repos: [], areas: [], sizes: [] };

export default function ActivityForm({
  open,
  steps,
  activities,
  users = [],
  githubOptions = EMPTY_OPTIONS,
  onClose,
  onSubmit,
}) {
  const [label, setLabel] = useState("");
  const [stepId, setStepId] = useState(steps[0]?.id || "");
  const [afterId, setAfterId] = useState("");
  const [dependsOnIds, setDependsOnIds] = useState([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [mode, setMode] = useState("manual");
  const [githubRepo, setGithubRepo] = useState("");
  const [area, setArea] = useState("");
  const [size, setSize] = useState("");
  const [resources, setResources] = useState([]);
  const [saving, setSaving] = useState(false);

  function updateResource(i, patch) {
    setResources((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }
  function removeResource(i) {
    setResources((prev) => prev.filter((_, j) => j !== i));
  }
  function addResource() {
    setResources((prev) => [...prev, { label: "", url: "" }]);
  }

  const stepActivities = activities.filter((a) => a.step === Number(stepId) || a.step === stepId);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({
        label,
        step_id: Number(stepId),
        after_id: afterId ? Number(afterId) : null,
        depends_on_ids: dependsOnIds.map(Number),
        assignee_id: assigneeId === "" ? null : Number(assigneeId),
        description,
        objectives,
        mode,
        github_repo: githubRepo,
        area,
        size,
        resources: resources
          .filter((r) => r.url.trim())
          .map((r) => ({ label: r.label.trim(), url: r.url.trim() })),
      });
      setLabel("");
      setDescription("");
      setObjectives("");
      setAfterId("");
      setDependsOnIds([]);
      setAssigneeId("");
      setMode("manual");
      setGithubRepo("");
      setArea("");
      setSize("");
      setResources([]);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  // freeSolo: aceita digitar valor fora da lista (áreas/sizes vêm vazias até o
  // token ganhar read:project; repos podem falhar no fetch)
  const soloProps = (options) => ({
    freeSolo: true,
    size: "small",
    fullWidth: true,
    options: options || [],
    disableClearable: false,
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={handleSubmit}>
        <DialogTitle>Add activity</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Label"
              size="small"
              required
              fullWidth
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <FormControl fullWidth size="small">
              <InputLabel>Step</InputLabel>
              <Select label="Step" value={stepId} onChange={(e) => setStepId(e.target.value)}>
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
                {stepActivities.map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    {a.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <DependsOnField activities={activities} value={dependsOnIds} onChange={setDependsOnIds} />
            <FormControl fullWidth size="small">
              <InputLabel>Assignee</InputLabel>
              <Select label="Assignee" value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)}>
                <MenuItem value="">Unassigned</MenuItem>
                {users.map((u) => (
                  <MenuItem key={u.id} value={u.id}>
                    {u.name || u.email}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl>
              <FormLabel>Mode</FormLabel>
              <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value)}>
                <FormControlLabel value="manual" control={<Radio size="small" />} label="Manual" />
                <FormControlLabel value="nifi" control={<Radio size="small" />} label="NiFi" />
              </RadioGroup>
            </FormControl>
            <Autocomplete
              {...soloProps(githubOptions.repos)}
              value={githubRepo}
              onInputChange={(_, v) => setGithubRepo(v)}
              renderInput={(params) => <TextField {...params} label="GitHub repo" size="small" />}
            />
            <Autocomplete
              {...soloProps(githubOptions.areas)}
              value={area}
              onInputChange={(_, v) => setArea(v)}
              renderInput={(params) => <TextField {...params} label="Area" size="small" />}
            />
            <Autocomplete
              {...soloProps(githubOptions.sizes)}
              value={size}
              onInputChange={(_, v) => setSize(v)}
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
                    sx={{ flex: 1 }}
                  />
                  <TextField
                    size="small"
                    label="URL"
                    placeholder="https://docs.google.com/…"
                    value={r.url}
                    onChange={(e) => updateResource(i, { url: e.target.value })}
                    sx={{ flex: 2 }}
                  />
                  <IconButton size="small" onClick={() => removeResource(i)} title="Remove resource">
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
              <Button size="small" startIcon={<AddIcon />} onClick={addResource}>
                Add resource
              </Button>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={saving || !label}>
            Add
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
