import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import EditIcon from "@mui/icons-material/Edit";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  Skeleton,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { releaseStatusLabel } from "../activityStatus";
import { downloadReport } from "../report";
import ActivityDagBoard from "../components/ActivityDagBoard";
import ActivityDrawer from "../components/ActivityDrawer";
import StepColorPicker from "../components/StepColorPicker";
import ActivityForm from "../components/ActivityForm";
import StepBoard from "../components/StepBoard";
import { defaultStepColor } from "../stepColors";

export default function ReleaseBoard({ releaseSlug, isStaff }) {
  const [release, setRelease] = useState(null);
  const [activities, setActivities] = useState([]);
  const [users, setUsers] = useState([]);
  const [githubOptions, setGithubOptions] = useState({ repos: [], areas: [], sizes: [] });
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [view, setView] = useState("kanban");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // anel de destaque no DAG: { id da activity editada, n incrementa a cada save }
  const [flash, setFlash] = useState(null);
  // dialogs de modo (draft/execução)
  const [stepOpen, setStepOpen] = useState(false);
  const [editStep, setEditStep] = useState(null);
  const [stepLabel, setStepLabel] = useState("");
  const [stepColor, setStepColor] = useState("");
  const [stepResources, setStepResources] = useState([]);
  const [startOpen, setStartOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  // modo de edição explícito da execução: Edit habilita, Save finaliza
  const [editMode, setEditMode] = useState(false);

  const doneCount = activities.filter((a) => a.status === "done").length;
  const draft = release?.status === "planned";
  const readonly = release?.status === "archived";
  const inExecution = release?.status === "active";
  // draft é sempre editável; na execução a edição é um modo explícito (Edit → Save)
  const canEdit = draft || (inExecution && editMode);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [rel, acts, us] = await Promise.all([
        api.get(`/api/releases/${releaseSlug}/`),
        api.get(`/api/releases/${releaseSlug}/activities/`),
        api.get("/api/external-identities/"),
      ]);
      setRelease(rel);
      setActivities(acts);
      setUsers(us);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
    // best-effort: falha nos options não derruba o board
    try {
      setGithubOptions(await api.get("/api/github/options/"));
    } catch {
      setGithubOptions({ repos: [], areas: [], sizes: [] });
    }
  }, [releaseSlug]);

  useEffect(() => {
    load();
  }, [load]);

  function selectActivity(activity) {
    setSelected(activity);
    window.history.replaceState(null, "", `?activity=${activity.id}`);
  }

  function closeDrawer() {
    setSelected(null);
    window.history.replaceState(null, "", window.location.pathname);
  }

  // restaura o drawer aberto ao carregar com ?activity=<id> na URL (F5 / link direto)
  useEffect(() => {
    if (!activities.length || selected) return;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("activity");
    if (id) {
      const act = activities.find((a) => a.id === Number(id));
      if (act) setSelected(act);
    }
  }, [activities, selected]);

  async function saveActivity(payload) {
    await api.patch(`/api/activities/${selected.id}/`, payload);
    setFlash((f) => ({ id: selected.id, n: (f?.n ?? 0) + 1 }));
    await load();
  }

  async function deleteActivity(activity) {
    await api.del(`/api/activities/${activity.id}/`);
    closeDrawer();
    await load();
  }

  async function moveActivity(activity, payload) {
    await api.post(`/api/activities/${activity.id}/move/`, payload);
    await load();
  }

  async function createActivity(payload) {
    setError("");
    try {
      await api.post(`/api/releases/${releaseSlug}/activities/`, payload);
      await load();
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  async function archive() {
    await api.patch(`/api/releases/${releaseSlug}/`, { status: "archived" });
    await load();
  }

  async function unarchive() {
    await api.patch(`/api/releases/${releaseSlug}/`, { status: "active" });
    await load();
  }

  async function download() {
    setError("");
    try {
      const transitions = await api.get(`/api/releases/${releaseSlug}/transitions/`);
      downloadReport(release, activities, transitions);
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveStep(e) {
    e.preventDefault();
    setError("");
    try {
      const resources = stepResources
        .filter((r) => r.url.trim())
        .map((r) => ({ label: r.label.trim(), url: r.url.trim() }));
      if (editStep) {
        await api.patch(`/api/releases/${releaseSlug}/steps/${editStep.id}/`, {
          label: stepLabel,
          color: stepColor,
          resources,
        });
      } else {
        await api.post(`/api/releases/${releaseSlug}/steps/`, {
          label: stepLabel,
          color: stepColor,
          resources,
        });
      }
      setStepOpen(false);
      setEditStep(null);
      setStepLabel("");
      setStepColor("");
      setStepResources([]);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function confirmDeleteStep() {
    if (!deleteTarget) return;
    setError("");
    try {
      await api.del(`/api/releases/${releaseSlug}/steps/${deleteTarget.id}/`);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function reorderStep(step, dir) {
    const steps = release?.steps || [];
    const idx = steps.findIndex((l) => l.id === step.id);
    const swap = steps[idx + dir];
    if (!swap) return;
    setError("");
    try {
      // troca a ordem das duas steps vizinhas
      await Promise.all([
        api.patch(`/api/releases/${releaseSlug}/steps/${step.id}/`, { order: swap.order }),
        api.patch(`/api/releases/${releaseSlug}/steps/${swap.id}/`, { order: step.order }),
      ]);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }


  async function startExecution() {
    setError("");
    try {
      await api.post(`/api/releases/${releaseSlug}/start/`);
      setStartOpen(false);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  const withoutAssignee = activities.filter((a) => !a.assignee).length;
  const withoutRepo = activities.filter((a) => !a.github_repo).length;

  if (loading && !release) {
    return (
      <Stack direction="row" spacing={2} sx={{ overflowX: "auto" }}>
        {[0, 1, 2, 3].map((i) => (
          <Stack key={i} spacing={1} sx={{ minWidth: 260 }}>
            <Skeleton variant="rounded" height={44} />
            <Skeleton variant="rounded" height={120} />
            <Skeleton variant="rounded" height={120} />
          </Stack>
        ))}
      </Stack>
    );
  }
  if (!release && error) return <Alert severity="error">{error}</Alert>;

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
        <div>
          <Typography variant="h5">{release?.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            Sequential gates: an activity cannot start until all prerequisites are done.
          </Typography>
        </div>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip
            label={releaseStatusLabel(release?.status)}
            color={
              release?.status === "active"
                ? "info"
                : release?.status === "completed"
                  ? "success"
                  : release?.status === "planned"
                    ? "warning"
                    : "default"
            }
          />
          <Stack direction="row" spacing={1} alignItems="center">
            <LinearProgress
              variant="determinate"
              value={activities.length ? (doneCount / activities.length) * 100 : 0}
              sx={{
                width: 140,
                height: 6,
                borderRadius: 3,
                "& .MuiLinearProgress-bar": { transition: "width 700ms ease" },
              }}
            />
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 70 }}>
              {doneCount}/{activities.length} done
            </Typography>
          </Stack>
          <ToggleButtonGroup size="small" exclusive value={view} onChange={(_, v) => v && setView(v)}>
            <ToggleButton value="kanban">Kanban</ToggleButton>
            <ToggleButton value="dag">DAG</ToggleButton>
          </ToggleButtonGroup>
          {canEdit && (
            <>
              <Button
                startIcon={<AddIcon />}
                variant="contained"
                onClick={() => {
                  setEditStep(null);
                  setStepLabel("");
                  setStepColor(defaultStepColor(release?.steps || []));
                  setStepResources([]);
                  setStepOpen(true);
                }}
              >
                Add step
              </Button>
              <Button startIcon={<AddIcon />} variant="contained" onClick={() => setAddOpen(true)}>
                Add activity
              </Button>
            </>
          )}
          {draft && isStaff && (
            <>
              <Button
                startIcon={<PlayArrowIcon />}
                variant="contained"
                color="success"
                onClick={() => setStartOpen(true)}
              >
                Start execution
              </Button>
              <Button variant="outlined" color="warning" onClick={archive}>
                Archive
              </Button>
            </>
          )}
          {inExecution &&
            (editMode ? (
              <Button startIcon={<SaveIcon />} variant="contained" onClick={() => setEditMode(false)}>
                Save
              </Button>
            ) : (
              <Button startIcon={<EditIcon />} variant="outlined" onClick={() => setEditMode(true)}>
                Edit
              </Button>
            ))}
          {inExecution && isStaff && (
            <Button variant="outlined" color="warning" onClick={archive}>
              Archive
            </Button>
          )}
          {release?.status === "completed" && isStaff && (
            <Button variant="outlined" color="warning" onClick={archive}>
              Archive
            </Button>
          )}
          {readonly && isStaff && (
            <Button variant="outlined" color="success" onClick={unarchive}>
              Unarchive
            </Button>
          )}
          <Button startIcon={<DownloadIcon />} variant="outlined" onClick={download}>
            Download report
          </Button>
        </Stack>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {draft && (
        <Alert severity="info">
          Draft — planning. Nothing is executed until you start the release.
        </Alert>
      )}
      {inExecution && release?.started_at && (
        <Alert severity="info">
          In execution · Started: {new Date(release.started_at).toLocaleString()}
          {editMode && " · Edit mode — changes are saved immediately; Save to finish."}
        </Alert>
      )}
      {release?.status === "completed" && (
        <Alert severity="success">
          Completed — all {activities.length} activity{activities.length === 1 ? "" : "ies"} are done.
        </Alert>
      )}
      {readonly && <Alert severity="info">This release is archived (read-only).</Alert>}
      {draft && !(release?.steps || []).length && (
        <Alert severity="info">Empty plan — add a step to start building it.</Alert>
      )}
      {view === "kanban" ? (
        <StepBoard
          steps={release?.steps || []}
          activities={activities}
          onSelect={selectActivity}
          editable={canEdit}
          onEditStep={(step) => {
            setEditStep(step);
            setStepLabel(step.label);
            setStepColor(step.color || "");
            setStepResources((step.resources || []).map((r) => ({ label: r.label || "", url: r.url || "" })));
            setStepOpen(true);
          }}
          onDeleteStep={(step) => setDeleteTarget(step)}
          onReorderStep={reorderStep}
        />
      ) : (
        <ActivityDagBoard
          steps={release?.steps || []}
          activities={activities}
          onSelect={selectActivity}
          selectedId={selected?.id ?? null}
          flash={flash}
        />
      )}
      <ActivityDrawer
        open={Boolean(selected)}
        activity={selected}
        releaseSlug={releaseSlug}
        users={users}
        githubOptions={githubOptions}
        steps={release?.steps || []}
        activities={activities}
        readonly={readonly}
        draft={draft}
        canEdit={canEdit}
        onClose={closeDrawer}
        onSave={saveActivity}
        onDelete={deleteActivity}
        onMove={moveActivity}
      />
      {canEdit && (
        <ActivityForm
          open={addOpen}
          steps={release?.steps || []}
          activities={activities}
          githubOptions={githubOptions}
          onClose={() => setAddOpen(false)}
          onSubmit={createActivity}
        />
      )}
      <Dialog open={stepOpen} onClose={() => setStepOpen(false)} fullWidth maxWidth="xs">
        <form onSubmit={saveStep}>
          <DialogTitle>{editStep ? "Edit step" : "Add step"}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField
                size="small"
                label="Label"
                value={stepLabel}
                onChange={(e) => setStepLabel(e.target.value)}
                required
                fullWidth
                autoFocus
              />
              <Stack spacing={1}>
                <Typography variant="overline">Color</Typography>
                <StepColorPicker value={stepColor} onChange={setStepColor} />
              </Stack>
              <Box>
                <Typography variant="overline">Resources</Typography>
                {stepResources.map((r, i) => (
                  <Stack key={i} direction="row" spacing={1} sx={{ mb: 1, alignItems: "flex-start" }}>
                    <TextField
                      size="small"
                      label="Label"
                      value={r.label}
                      onChange={(e) =>
                        setStepResources((prev) => prev.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))
                      }
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      size="small"
                      label="URL"
                      placeholder="https://docs.google.com/…"
                      value={r.url}
                      onChange={(e) =>
                        setStepResources((prev) => prev.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))
                      }
                      sx={{ flex: 2 }}
                    />
                    <IconButton
                      size="small"
                      onClick={() => setStepResources((prev) => prev.filter((_, j) => j !== i))}
                      title="Remove resource"
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
                <Button
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={() => setStepResources((prev) => [...prev, { label: "", url: "" }])}
                >
                  Add resource
                </Button>
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setStepOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={!stepLabel}>
              {editStep ? "Save" : "Add"}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Delete step</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete step "{deleteTarget?.label}"? Only empty steps can be removed.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDeleteStep}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={startOpen} onClose={() => setStartOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Start execution?</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2">
              {activities.length} activities · {withoutAssignee} without assignee · {withoutRepo} without GitHub repo
            </Typography>
            <Typography variant="body2" color="text.secondary">
              The release goes into operation: activities can start progressing. The plan stays editable at any
              time — starting is an indication that it is live, not a freeze.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartOpen(false)}>Cancel</Button>
          <Button variant="contained" color="success" onClick={startExecution}>
            Start execution
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
