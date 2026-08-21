import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SearchIcon from "@mui/icons-material/Search";
import UploadFileIcon from "@mui/icons-material/UploadFile";
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
  FormHelperText,
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
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api, appUrl } from "../api";
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
  draft: "warning",
  active: "info",
  completed: "success",
  archived: "default",
};

const PAGES = {
  releases: {
    title: "Releases",
    subtitle: "Official data releases — in execution and completed.",
    empty: "No releases yet.",
    statuses: ["active", "completed"],
  },
  drafts: {
    title: "Drafts",
    subtitle: "Plan the next release. Drafts can be deleted.",
    empty: "No drafts yet.",
    statuses: ["draft"],
  },
  archived: {
    title: "Archived",
    subtitle: "Frozen releases. Restore from the board.",
    empty: "No archived releases.",
    statuses: ["archived"],
  },
};

function ReleaseCard({ rel, onDelete }) {
  return (
    <Card elevation={2}>
      <CardActionArea href={appUrl(`/releases/${rel.slug}/`)}>
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
      {rel.status === "draft" && (
        <CardActions sx={{ justifyContent: "flex-end", pt: 0 }}>
          <IconButton size="small" title="Delete draft" onClick={() => onDelete(rel)}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </CardActions>
      )}
    </Card>
  );
}

export default function ReleaseList({ page = "releases" }) {
  const [releases, setReleases] = useState([]);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  // origem do novo draft: blank | release | json
  const [origin, setOrigin] = useState("blank");
  const [copyReleaseSlug, setCopyReleaseSlug] = useState("");
  // draft lido do arquivo JSON (origem "json") e erro de leitura/parse
  const [importedDraft, setImportedDraft] = useState(null);
  const [jsonError, setJsonError] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
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

  function handleDraftFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // permite escolher o mesmo arquivo de novo
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const draft = JSON.parse(reader.result);
        if (!Array.isArray(draft.steps) || !Array.isArray(draft.activities)) {
          setJsonError("This file needs a steps list and an activities list.");
          setImportedDraft(null);
          return;
        }
        setImportedDraft(draft);
        setJsonError("");
        // o nome do arquivo vira sugestão; o usuário pode trocar
        if (!name && draft.name) setName(draft.name);
      } catch {
        setJsonError("This file isn't valid JSON.");
        setImportedDraft(null);
      }
    };
    reader.readAsText(file);
  }

  async function createRelease(e) {
    e.preventDefault();
    setError("");
    try {
      if (origin === "json") {
        await api.post("/api/releases/import/", {
          name,
          steps: importedDraft.steps,
          activities: importedDraft.activities,
        });
      } else {
        const payload = { name };
        if (origin === "release") payload.copy_from_release_slug = copyReleaseSlug;
        await api.post("/api/releases/", payload);
      }
      setName("");
      setOrigin("blank");
      setCopyReleaseSlug("");
      setImportedDraft(null);
      setJsonError("");
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

  const canCreate =
    Boolean(name) &&
    (origin === "blank" || (origin === "release" && copyReleaseSlug) || (origin === "json" && importedDraft));

  const pageDef = PAGES[page] || PAGES.releases;
  const q = query.trim().toLowerCase();
  const items = releases.filter(
    (r) =>
      pageDef.statuses.includes(r.status) &&
      (!q || r.name.toLowerCase().includes(q) || (r.template_key || "").toLowerCase().includes(q)),
  );
  const running = items.filter((r) => r.status === "active");
  const completed = items.filter((r) => r.status === "completed");
  const copySources = releases.filter((r) => r.status !== "draft");

  function renderCards(list) {
    return (
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "1fr" }}>
        {list.map((rel) => (
          <ReleaseCard key={rel.id} rel={rel} onDelete={setDeleteTarget} />
        ))}
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <div>
          <Typography variant="h5">{pageDef.title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {pageDef.subtitle}
          </Typography>
        </div>
        <TextField
          size="small"
          placeholder="Search"
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
        {page === "drafts" && (
          <Button startIcon={<AddIcon />} variant="contained" onClick={() => setOpen(true)}>
            New draft
          </Button>
        )}
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {loading && <LinearProgress />}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New draft</DialogTitle>
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
                <FormControlLabel value="blank" control={<Radio size="small" />} label="Blank draft" />
                <FormControlLabel value="release" control={<Radio size="small" />} label="Previous release" />
                <FormControlLabel value="json" control={<Radio size="small" />} label="JSON file" />
              </RadioGroup>
            </FormControl>
            {origin === "json" && (
              <FormControl size="small">
                <Button component="label" variant="outlined" size="small" startIcon={<UploadFileIcon />}>
                  Choose JSON file
                  <input type="file" accept=".json,application/json" hidden onChange={handleDraftFile} />
                </Button>
                {jsonError ? (
                  <FormHelperText error>{jsonError}</FormHelperText>
                ) : (
                  importedDraft && (
                    <FormHelperText>
                      {importedDraft.name ? `Loaded ${importedDraft.name}.` : "Draft loaded."}
                    </FormHelperText>
                  )
                )}
              </FormControl>
            )}
            {origin === "release" && (
              <FormControl size="small" fullWidth>
                <InputLabel>Previous release</InputLabel>
                <Select
                  label="Previous release"
                  value={copyReleaseSlug}
                  onChange={(e) => setCopyReleaseSlug(e.target.value)}
                >
                  {copySources.map((r) => (
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
      {page === "releases" && !loading && (
        <Stack spacing={3}>
          <Stack spacing={1}>
            <Typography variant="subtitle2">In execution ({running.length})</Typography>
            {running.length ? renderCards(running) : (
              <Typography variant="body2" color="text.secondary">
                None in execution.
              </Typography>
            )}
          </Stack>
          <Stack spacing={1}>
            <Typography variant="subtitle2">Completed ({completed.length})</Typography>
            {completed.length ? renderCards(completed) : (
              <Typography variant="body2" color="text.secondary">
                No completed releases.
              </Typography>
            )}
          </Stack>
        </Stack>
      )}
      {page !== "releases" && !items.length && !loading && (
        <Typography variant="body2" color="text.secondary">
          {pageDef.empty}
        </Typography>
      )}
      {page !== "releases" && renderCards(items)}
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Delete draft</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            "{deleteTarget?.name}" and its steps, activities, and history will be deleted. This can't be
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
