import AddIcon from "@mui/icons-material/Add";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";
import { releaseStatusLabel } from "../activityStatus";

// estado de uma lane pelo percentual de atividades concluídas
function laneStatus(pct) {
  if (pct >= 100) return "completed";
  if (pct > 0) return "in progress";
  return "waiting";
}

const LANE_STATUS_LABELS = {
  waiting: "Waiting",
  "in progress": "In Progress",
  completed: "Completed",
};

export default function ReleaseList() {
  const [releases, setReleases] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [r, t] = await Promise.all([api.get("/api/releases/"), api.get("/api/templates/")]);
      setReleases(r);
      setTemplates(t);
      if (!templateId && t.length) setTemplateId(t[0].id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createRelease(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/releases/", { name, template_id: Number(templateId) });
      setName("");
      setOpen(false);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <div>
          <Typography variant="h5">Data Releases</Typography>
          <Typography variant="body2" color="text.secondary">
            Track progress across LSST data release workflows.
          </Typography>
        </div>
        <Button startIcon={<AddIcon />} variant="contained" onClick={() => setOpen(true)}>
          Create release
        </Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {loading && <LinearProgress />}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Create release from template</DialogTitle>
        <DialogContent>
          <Stack component="form" id="create-release-form" onSubmit={createRelease} spacing={2} sx={{ pt: 1 }}>
            <TextField
              size="small"
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              fullWidth
            />
            <FormControl size="small" fullWidth>
              <InputLabel>Template</InputLabel>
              <Select label="Template" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                {templates.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" form="create-release-form" variant="contained" disabled={!name || !templateId}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: "1fr",
        }}
      >
        {releases.map((rel) => (
          <Card key={rel.id} elevation={2}>
            <CardActionArea href={`/releases/${rel.slug}/`}>
              <CardContent>
                <Stack spacing={1}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6">{rel.name}</Typography>
                    <Chip
                      size="small"
                      label={releaseStatusLabel(rel.status)}
                      color={
                        rel.status === "active"
                          ? "info"
                          : rel.status === "completed"
                            ? "success"
                            : "default"
                      }
                    />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Template: {rel.template_key || "—"}
                  </Typography>
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(165px, 1fr))",
                      gap: 1,
                      pb: 0.5,
                    }}
                  >
                    {(rel.lanes || [])
                      .filter((l) => l.progress?.total)
                      .map((lane) => {
                        const pct = lane.progress?.pct || 0;
                        const status = laneStatus(pct);
                        const active = status !== "waiting";
                        return (
                          <Box
                            key={lane.id}
                            sx={{
                              width: "100%",
                              border: 1,
                              borderColor: "divider",
                              borderRadius: 1,
                              overflow: "hidden",
                              // lanes que ainda não começaram ficam desativadas
                              opacity: active ? 1 : 0.45,
                            }}
                          >
                            <Box
                              sx={{
                                bgcolor: active ? lane.color || "#000099" : "action.hover",
                                // no cinza claro dos desativados o branco não legível: título em cinza escuro
                                color: active ? "#fff" : "grey.800",
                                px: 1,
                                py: 0.5,
                              }}
                            >
                              <Typography
                                variant="caption"
                                noWrap
                                sx={{ display: "block", fontWeight: 700, fontSize: 11 }}
                              >
                                {lane.label}
                              </Typography>
                            </Box>
                            <Stack spacing={0.5} sx={{ px: 1, py: 0.75 }}>
                              <Stack direction="row" alignItems="center" justifyContent="space-between">
                                <Typography
                                  variant="caption"
                                  color={
                                    status === "completed"
                                      ? "success.main"
                                      : status === "in progress"
                                        ? "info.main"
                                        : "text.secondary"
                                  }
                                >
                                  {LANE_STATUS_LABELS[status] || status}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {Math.round(pct)}%
                                </Typography>
                              </Stack>
                              <LinearProgress
                                variant="determinate"
                                value={pct}
                                color={status === "completed" ? "success" : "primary"}
                                sx={{ height: 4, borderRadius: 1 }}
                              />
                            </Stack>
                          </Box>
                        );
                      })}
                  </Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="caption" fontWeight={600}>
                      Progress
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={rel.progress?.pct || 0}
                      sx={{ flex: 1, height: 8, borderRadius: 1 }}
                    />
                    <Typography variant="caption" sx={{ minWidth: 38, textAlign: "right" }}>
                      {rel.progress?.pct || 0}%
                    </Typography>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {rel.progress?.done || 0}/{rel.progress?.total || 0} activities done
                  </Typography>
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </Box>
    </Stack>
  );
}
