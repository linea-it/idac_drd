import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import AddIcon from "@mui/icons-material/Add";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";

export default function TemplateEditor({ isStaff }) {
  const [templates, setTemplates] = useState([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [template, setTemplate] = useState(null);
  const [label, setLabel] = useState("");
  const [laneKey, setLaneKey] = useState("");
  const [dependsOn, setDependsOn] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [editStage, setEditStage] = useState(null);
  const [editLabel, setEditLabel] = useState("");
  const [editLaneKey, setEditLaneKey] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editOrder, setEditOrder] = useState("");
  const [editDependsOn, setEditDependsOn] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newKey, setNewKey] = useState("");
  const [tplName, setTplName] = useState("");
  const [tplVersion, setTplVersion] = useState(1);
  const [tplActive, setTplActive] = useState(true);
  const [laneLabel, setLaneLabel] = useState("");
  const [laneKeyNew, setLaneKeyNew] = useState("");
  const [laneOrder, setLaneOrder] = useState("");
  const [laneColor, setLaneColor] = useState("");
  const [editLane, setEditLane] = useState(null);
  const [editLaneLabel, setEditLaneLabel] = useState("");
  const [editLaneOrder, setEditLaneOrder] = useState("");
  const [editLaneColor, setEditLaneColor] = useState("");

  async function load() {
    const list = await api.get("/api/templates/");
    setTemplates(list);
    const key = selectedKey || list[0]?.key;
    if (key) {
      await selectTemplate(key, list);
    } else {
      setSelectedKey("");
      setTemplate(null);
    }
  }

  async function selectTemplate(key, list) {
    setSelectedKey(key);
    setError("");
    const detail = await api.get(`/api/templates/${key}/`);
    setTemplate(detail);
    setLaneKey(detail.lanes[0]?.key || "");
    setTplName(detail.name);
    setTplVersion(detail.version);
    setTplActive(detail.is_active);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function createTemplate(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      const t = await api.post("/api/templates/", {
        name: newName,
        key: newKey || undefined,
      });
      setNewOpen(false);
      setNewName("");
      setNewKey("");
      setInfo(`Template "${t.name}" created. Add lanes and stages to define the workflow.`);
      await selectTemplate(t.key);
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveTemplate(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.patch(`/api/templates/${selectedKey}/`, {
        name: tplName,
        version: tplVersion === "" ? 1 : Number(tplVersion),
        is_active: tplActive,
      });
      setInfo("Template saved.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteTemplate() {
    if (!window.confirm(`Delete template "${template?.name}"? Its lanes and stages will be removed.`)) return;
    setError("");
    setInfo("");
    try {
      await api.del(`/api/templates/${selectedKey}/`);
      setSelectedKey("");
      setTemplate(null);
      setInfo("Template deleted.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function addStage(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.post(`/api/templates/${selectedKey}/stages/`, {
        label,
        lane_key: laneKey,
        depends_on: dependsOn ? dependsOn.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      setLabel("");
      setDependsOn("");
      setInfo("Stage added. New releases will include it.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  function openEdit(stage) {
    setEditStage(stage);
    setEditLabel(stage.label);
    setEditLaneKey(stage.lane_key);
    setEditDescription(stage.description || "");
    setEditOrder(stage.order);
    setEditDependsOn((stage.depends_on || []).join(", "));
    setError("");
  }

  async function saveEdit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.patch(`/api/templates/${selectedKey}/stages/${editStage.id}/`, {
        label: editLabel,
        lane_key: editLaneKey,
        description: editDescription,
        order: editOrder === "" ? undefined : Number(editOrder),
        depends_on: editDependsOn ? editDependsOn.split(",").map((s) => s.trim()).filter(Boolean) : [],
      });
      setEditStage(null);
      setInfo("Stage updated.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteStage(stage) {
    if (!window.confirm(`Delete stage "${stage.label}"?`)) return;
    setError("");
    setInfo("");
    try {
      await api.del(`/api/templates/${selectedKey}/stages/${stage.id}/`);
      setInfo("Stage deleted.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  async function addLane(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.post(`/api/templates/${selectedKey}/lanes/`, {
        label: laneLabel,
        key: laneKeyNew || undefined,
        order: laneOrder === "" ? undefined : Number(laneOrder),
        color: laneColor,
      });
      setLaneLabel("");
      setLaneKeyNew("");
      setLaneOrder("");
      setLaneColor("");
      setInfo("Lane added.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  function openLaneEdit(lane) {
    setEditLane(lane);
    setEditLaneLabel(lane.label);
    setEditLaneOrder(lane.order);
    setEditLaneColor(lane.color || "");
    setError("");
  }

  async function saveLaneEdit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.patch(`/api/templates/${selectedKey}/lanes/${editLane.id}/`, {
        label: editLaneLabel,
        order: editLaneOrder === "" ? undefined : Number(editLaneOrder),
        color: editLaneColor,
      });
      setEditLane(null);
      setInfo("Lane updated.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteLane(lane) {
    if (!window.confirm(`Delete lane "${lane.label}"? Its stages will also be deleted.`)) return;
    setError("");
    setInfo("");
    try {
      await api.del(`/api/templates/${selectedKey}/lanes/${lane.id}/`);
      setInfo("Lane deleted.");
      await selectTemplate(selectedKey);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems="flex-start" spacing={1}>
        <div>
          <Typography variant="h5">Workflow Templates</Typography>
          <Typography variant="body2" color="text.secondary">
            Edit the process definitions used when creating new data releases.
          </Typography>
        </div>
        {isStaff && (
          <Button startIcon={<AddIcon />} variant="contained" onClick={() => setNewOpen(true)}>
            New template
          </Button>
        )}
      </Stack>
      {!isStaff && (
        <Alert severity="info">View only. Staff permission required to edit templates.</Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      {info && <Alert severity="success">{info}</Alert>}
      <FormControl size="small" sx={{ maxWidth: 360 }}>
        <InputLabel>Template</InputLabel>
        <Select label="Template" value={selectedKey} onChange={(e) => selectTemplate(e.target.value)}>
          {templates.map((t) => (
            <MenuItem key={t.key} value={t.key}>
              {t.name} (v{t.version})
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {template && (
        <>
          {isStaff && (
            <Card elevation={2}>
              <CardContent>
                <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems="flex-start" spacing={1}>
                  <Typography variant="subtitle1" gutterBottom>
                    Template settings
                  </Typography>
                  <Button color="error" size="small" onClick={deleteTemplate} startIcon={<DeleteIcon />}>
                    Delete template
                  </Button>
                </Stack>
                <Stack component="form" onSubmit={saveTemplate} spacing={2} sx={{ mt: 1 }}>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                    <TextField
                      size="small"
                      label="Name"
                      value={tplName}
                      onChange={(e) => setTplName(e.target.value)}
                      required
                      fullWidth
                    />
                    <TextField
                      size="small"
                      label="Version"
                      type="number"
                      value={tplVersion}
                      onChange={(e) => setTplVersion(e.target.value)}
                      sx={{ minWidth: 120 }}
                    />
                  </Stack>
                  <FormControlLabel
                    control={
                      <Checkbox size="small" checked={tplActive} onChange={(e) => setTplActive(e.target.checked)} />
                    }
                    label="Active"
                  />
                  <Button type="submit" variant="contained" disabled={!tplName} sx={{ alignSelf: "flex-start" }}>
                    Save template
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          )}
          <Card elevation={2}>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                Lanes ({template.lanes.length})
              </Typography>
              <Stack spacing={1} sx={{ mb: 2 }}>
                {template.lanes.map((l) => (
                  <Stack key={l.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Box
                      sx={{ width: 14, height: 14, borderRadius: "50%", bgcolor: l.color || "#0989cb" }}
                    />
                    <Typography variant="body2" fontWeight={600}>
                      {l.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {l.key} · order {l.order}
                    </Typography>
                    {isStaff && (
                      <>
                        <IconButton size="small" onClick={() => openLaneEdit(l)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton size="small" color="error" onClick={() => deleteLane(l)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </>
                    )}
                  </Stack>
                ))}
              </Stack>
              {isStaff && (
                <Stack component="form" onSubmit={addLane} spacing={2}>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                    <TextField
                      size="small"
                      label="Label"
                      value={laneLabel}
                      onChange={(e) => setLaneLabel(e.target.value)}
                      required
                      fullWidth
                    />
                    <TextField
                      size="small"
                      label="Key"
                      value={laneKeyNew}
                      onChange={(e) => setLaneKeyNew(e.target.value)}
                      helperText="Auto-generated from label if empty"
                    />
                    <TextField
                      size="small"
                      label="Order"
                      type="number"
                      value={laneOrder}
                      onChange={(e) => setLaneOrder(e.target.value)}
                      sx={{ minWidth: 90 }}
                    />
                    <TextField
                      size="small"
                      label="Color"
                      value={laneColor}
                      onChange={(e) => setLaneColor(e.target.value)}
                      helperText="e.g. #CC0000"
                      sx={{ minWidth: 130 }}
                    />
                  </Stack>
                  <Button type="submit" variant="contained" disabled={!laneLabel} sx={{ alignSelf: "flex-start" }}>
                    Add lane
                  </Button>
                </Stack>
              )}
            </CardContent>
          </Card>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="subtitle1" gutterBottom>
                Stages ({template.stages.length})
              </Typography>
              <Stack spacing={1}>
                {template.stages.map((s) => (
                  <Stack key={s.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Chip size="small" label={s.lane_key} />
                    <Typography variant="body2" fontWeight={600}>
                      {s.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      deps: {(s.depends_on || []).join(", ") || "—"}
                    </Typography>
                    {isStaff && (
                      <>
                        <IconButton size="small" onClick={() => openEdit(s)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton size="small" color="error" onClick={() => deleteStage(s)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </>
                    )}
                  </Stack>
                ))}
              </Stack>
            </CardContent>
          </Card>
          {isStaff && (
            <Card elevation={2}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom>
                  Add stage to template
                </Typography>
                <Stack component="form" onSubmit={addStage} spacing={2}>
                  <TextField
                    size="small"
                    label="Label"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    required
                  />
                  <FormControl size="small">
                    <InputLabel>Lane</InputLabel>
                    <Select label="Lane" value={laneKey} onChange={(e) => setLaneKey(e.target.value)}>
                      {template.lanes.map((l) => (
                        <MenuItem key={l.key} value={l.key}>
                          {l.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    size="small"
                    label="Depends on (comma-separated keys)"
                    value={dependsOn}
                    onChange={(e) => setDependsOn(e.target.value)}
                    helperText="Example: approve-qa-parquet, convert-hats"
                  />
                  <Button type="submit" variant="contained" disabled={!label}>
                    Add stage
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          )}
        </>
      )}
      <Dialog open={newOpen} onClose={() => setNewOpen(false)} fullWidth maxWidth="sm">
        <form onSubmit={createTemplate}>
          <DialogTitle>New template</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                size="small"
                label="Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
              />
              <TextField
                size="small"
                label="Key"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                helperText="Auto-generated from name if empty"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setNewOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={!newName}>
              Create
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <Dialog open={Boolean(editStage)} onClose={() => setEditStage(null)} fullWidth maxWidth="sm">
        <form onSubmit={saveEdit}>
          <DialogTitle>Edit stage</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                size="small"
                label="Label"
                value={editLabel}
                onChange={(e) => setEditLabel(e.target.value)}
                required
              />
              <FormControl size="small">
                <InputLabel>Lane</InputLabel>
                <Select label="Lane" value={editLaneKey} onChange={(e) => setEditLaneKey(e.target.value)}>
                  {template?.lanes.map((l) => (
                    <MenuItem key={l.key} value={l.key}>
                      {l.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                size="small"
                label="Description"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                multiline
                minRows={2}
              />
              <TextField
                size="small"
                label="Order"
                type="number"
                value={editOrder}
                onChange={(e) => setEditOrder(e.target.value)}
              />
              <TextField
                size="small"
                label="Depends on (comma-separated keys)"
                value={editDependsOn}
                onChange={(e) => setEditDependsOn(e.target.value)}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditStage(null)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={!editLabel}>
              Save
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <Dialog open={Boolean(editLane)} onClose={() => setEditLane(null)} fullWidth maxWidth="sm">
        <form onSubmit={saveLaneEdit}>
          <DialogTitle>Edit lane</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                size="small"
                label="Label"
                value={editLaneLabel}
                onChange={(e) => setEditLaneLabel(e.target.value)}
                required
              />
              <TextField
                size="small"
                label="Order"
                type="number"
                value={editLaneOrder}
                onChange={(e) => setEditLaneOrder(e.target.value)}
              />
              <TextField
                size="small"
                label="Color"
                value={editLaneColor}
                onChange={(e) => setEditLaneColor(e.target.value)}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditLane(null)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={!editLaneLabel}>
              Save
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </Stack>
  );
}
