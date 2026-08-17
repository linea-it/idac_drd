import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SearchIcon from "@mui/icons-material/Search";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardActions,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputAdornment,
  InputLabel,
  LinearProgress,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";
import { releaseStatusLabel } from "../activityStatus";

// estado de um step pelo percentual de atividades concluídas
function stepStatus(pct) {
  if (pct >= 100) return "completed";
  if (pct > 0) return "in progress";
  return "todo";
}

const STEP_STATUS_LABELS = {
  todo: "To do",
  "in progress": "In Progress",
  completed: "Completed",
};

const CHIP_COLORS = {
  planned: "warning",
  active: "info",
  completed: "success",
  archived: "default",
};

// abas: drafts descartáveis | histórico oficial | arquivado
const TABS = [
  { key: "plans", statuses: ["planned"], empty: "No plans yet." },
  { key: "releases", statuses: ["active", "completed"], empty: "No releases yet." },
  { key: "archived", statuses: ["archived"], empty: "No archived releases." },
];

function ReleaseCard({ rel, onDelete }) {
  return (
    <Card elevation={2}>
      <CardActionArea href={`/releases/${rel.slug}/`}>
        <CardContent>
          <Stack spacing={1}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6">{rel.name}</Typography>
              <Chip size="small" label={releaseStatusLabel(rel.status)} color={CHIP_COLORS[rel.status]} />
            </Stack>
            {rel.template_key && (
              <Typography variant="body2" color="text.secondary">
                Based on template: {rel.template_key}
              </Typography>
            )}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(165px, 1fr))",
                gap: 1,
                pb: 0.5,
              }}
            >
              {(rel.steps || [])
                .filter((l) => l.progress?.total)
                .map((step) => {
                  const pct = step.progress?.pct || 0;
                  const status = stepStatus(pct);
                  const active = status !== "todo";
                  return (
                    <Box
                      key={step.id}
                      sx={{
                        width: "100%",
                        border: 1,
                        borderColor: "divider",
                        borderRadius: 1,
                        overflow: "hidden",
                        // steps que ainda não começaram ficam desativados
                        opacity: active ? 1 : 0.45,
                      }}
                    >
                      <Box
                        sx={{
                          bgcolor: active ? step.color || "#000099" : "action.hover",
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
                          {step.label}
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
                            {STEP_STATUS_LABELS[status] || status}
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
      {rel.status === "planned" && (
        <CardActions sx={{ justifyContent: "flex-end", pt: 0 }}>
          <IconButton size="small" title="Delete plan" onClick={() => onDelete(rel)}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </CardActions>
      )}
    </Card>
  );
}

export default function ReleaseList() {
  const [releases, setReleases] = useState([]);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  // origem do novo plano: blank | release
  const [origin, setOrigin] = useState("blank");
  const [copyReleaseSlug, setCopyReleaseSlug] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("releases");
  const [deleteTarget, setDeleteTarget] = useState(null);

  async function load() {
    setLoading(true);
    try {
      setReleases(await api.get("/api/releases/"));
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
      const payload = { name };
      if (origin === "release") payload.copy_from_release_slug = copyReleaseSlug;
      await api.post("/api/releases/", payload);
      setName("");
      setOrigin("blank");
      setCopyReleaseSlug("");
      setOpen(false);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setError("");
    try {
      await api.del(`/api/releases/${deleteTarget.slug}/`);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setError(err.message);
      setDeleteTarget(null);
    }
  }

  const canCreate = Boolean(name) && (origin === "blank" || (origin === "release" && copyReleaseSlug));

  const tabDef = TABS.find((t) => t.key === tab);
  const counts = {
    plans: releases.filter((r) => r.status === "planned").length,
    releases: releases.filter((r) => ["active", "completed"].includes(r.status)).length,
    archived: releases.filter((r) => r.status === "archived").length,
  };

  const q = query.trim().toLowerCase();
  const items = releases.filter(
    (r) =>
      tabDef.statuses.includes(r.status) &&
      (!q || r.name.toLowerCase().includes(q) || (r.template_key || "").toLowerCase().includes(q)),
  );

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <div>
          <Typography variant="h5">Data Releases</Typography>
          <Typography variant="body2" color="text.secondary">
            Track progress across LSST data release workflows.
          </Typography>
        </div>
        <TextField
          size="small"
          placeholder="Search releases"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          sx={{ minWidth: 220 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        <Button startIcon={<AddIcon />} variant="contained" onClick={() => setOpen(true)}>
          Create release
        </Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {loading && <LinearProgress />}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New release</DialogTitle>
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
            <FormControl>
              <FormLabel>Start from</FormLabel>
              <RadioGroup row value={origin} onChange={(e) => setOrigin(e.target.value)}>
                <FormControlLabel value="blank" control={<Radio size="small" />} label="Blank plan" />
                <FormControlLabel value="release" control={<Radio size="small" />} label="Previous release" />
              </RadioGroup>
            </FormControl>
            {origin === "release" && (
              <FormControl size="small" fullWidth>
                <InputLabel>Previous release</InputLabel>
                <Select
                  label="Previous release"
                  value={copyReleaseSlug}
                  onChange={(e) => setCopyReleaseSlug(e.target.value)}
                >
                  {releases.map((r) => (
                    <MenuItem key={r.slug} value={r.slug}>
                      {r.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" form="create-release-form" variant="contained" disabled={!canCreate}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab label={`Releases (${counts.releases})`} value="releases" />
        <Tab label={`Plans (${counts.plans})`} value="plans" />
        <Tab label={`Archived (${counts.archived})`} value="archived" />
      </Tabs>
      {!items.length && !loading && (
        <Typography variant="body2" color="text.secondary">
          {tabDef.empty}
        </Typography>
      )}
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "1fr" }}>
        {items.map((rel) => (
          <ReleaseCard key={rel.id} rel={rel} onDelete={setDeleteTarget} />
        ))}
      </Box>
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Delete plan</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete plan "{deleteTarget?.name}"? This removes its steps, activities and history — it cannot be
            undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDelete}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
