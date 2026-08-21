import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
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
import { api, appUrl } from "../api";
import { releaseStatusLabel } from "../activityStatus";
import { downloadReport, downloadTextFile } from "../report";
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
  const [githubError, setGithubError] = useState("");
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
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteDraftOpen, setDeleteDraftOpen] = useState(false);
  // modo de edição explícito da execução: Edit habilita, Save finaliza
  const [editMode, setEditMode] = useState(false);

  const doneCount = activities.filter((a) => a.status === "done").length;
  const draft = release?.status === "draft";
  const readonly = release?.status === "archived";
  const inExecution = release?.status === "active";
  const completed = release?.status === "completed";
  // draft é sempre editável; em active/completed a edição é um modo explícito (Edit → Save)
  const canEdit = draft || ((inExecution || completed) && editMode);

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
    // best-effort: falha nos options não derruba o board; erro vira banner
    try {
      const opts = await api.get("/api/github/options/");
      setGithubOptions(opts);
      setGithubError(opts.error ? `GitHub: ${opts.error}` : "");
    } catch (err) {
      setGithubOptions({ repos: [], areas: [], sizes: [] });
      setGithubError(err.message);
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

  async function duplicateActivity(activity) {
    setError("");
    try {
      const copy = await api.post(`/api/activities/${activity.id}/duplicate/`, {});
      await load();
      selectActivity(copy);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  // reordenação do Kanban (setas ↑/↓): move uma posição dentro do step
  function moveActivityDir(activity, dir) {
    const acts = activities
      .filter((a) => a.step === activity.step)
      .sort((a, b) => a.order - b.order);
    const i = acts.findIndex((a) => a.id === activity.id);
    const after = dir < 0 ? acts[i - 2] : acts[i + 1];
    moveActivity(activity, { step_id: activity.step, after_id: after ? after.id : null });
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

  async function confirmDeleteDraft() {
    setError("");
    try {
      await api.del(`/api/releases/${releaseSlug}/`);
      window.location.href = document.querySelector(".navbar-brand")?.getAttribute("href") || appUrl("/");
    } catch (err) {
      setError(err.message);
      setDeleteDraftOpen(false);
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
      const [transitions, textRevisions] = await Promise.all([
        api.get(`/api/releases/${releaseSlug}/transitions/`),
        api.get(`/api/releases/${releaseSlug}/text-revisions/`),
      ]);
      downloadReport(release, activities, transitions, textRevisions);
    } catch (err) {
      setError(err.message);
    }
  }

  async function exportDraft() {
    setError("");
    try {
      const payload = await api.get(`/api/releases/${releaseSlug}/export/`);
      downloadTextFile(
        `${release.slug || releaseSlug}-draft.json`,
        JSON.stringify(payload, null, 2),
        "application/json;charset=utf-8",
      );
    } catch (err) {
      setError(err.message);
    }
  }

  function cancelEdit() {
    // desiste do modo de edição: recarrega do servidor (alterações já feitas
    // foram salvas imediatamente; o reload devolve o estado real)
    setEditMode(false);
    load();
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
    setError("");
    try {
      await api.patch(`/api/releases/${releaseSlug}/steps/${step.id}/`, { direction: dir });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }


  async function renameRelease() {
    setError("");
    try {
      await api.patch(`/api/releases/${releaseSlug}/`, { name: renameName.trim() });
      setRenameOpen(false);
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
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h5">{release?.name}</Typography>
            {release?.status === "draft" && (
              <IconButton
                size="small"
                title="Rename release"
                onClick={() => {
                  setRenameName(release?.name || "");
                  setRenameOpen(true);
                }}
              >
                <EditIcon fontSize="small" />
              </IconButton>
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Sequential gates: an activity cannot start until all prerequisites are done.
          </Typography>
        </div>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip
            label={releaseStatusLabel(release?.status)}
            color={
              release?.status === "active"
                ? "info"
                : release?.status === "completed"
                  ? "success"
                  : release?.status === "draft"
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
          {/* construção: adicionar steps/atividades (draft ou modo de edição) */}
          {(draft || editMode) && (
            <>
              <Button
                startIcon={<AddIcon />}
                variant="contained"
                sx={{ whiteSpace: "nowrap" }}
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
              <Button
                startIcon={<AddIcon />}
                variant="contained"
                sx={{ whiteSpace: "nowrap" }}
                onClick={() => setAddOpen(true)}
              >
                Add activity
              </Button>
            </>
          )}
          {/* ciclo de vida: iniciar/arquivar/desarquivar */}
          {draft && isStaff && (
            <Button
              startIcon={<PlayArrowIcon />}
              variant="contained"
              color="success"
              sx={{ whiteSpace: "nowrap" }}
              onClick={() => setStartOpen(true)}
            >
              Start execution
            </Button>
          )}
          {(inExecution || completed) && isStaff && (
            <Button variant="outlined" color="warning" sx={{ whiteSpace: "nowrap" }} onClick={archive}>
              Archive
            </Button>
          )}
          {draft && (
            <Button
              startIcon={<DeleteIcon />}
              variant="outlined"
              color="error"
              sx={{ whiteSpace: "nowrap" }}
              onClick={() => setDeleteDraftOpen(true)}
            >
              Delete draft
            </Button>
          )}
          {readonly && isStaff && (
            <Button variant="outlined" color="success" sx={{ whiteSpace: "nowrap" }} onClick={unarchive}>
              Unarchive
            </Button>
          )}
          {/* modo de edição: Edit → Cancel (descarta) + Save (finaliza) */}
          {(inExecution || completed) &&
            (editMode ? (
              // par de ação: Cancel e Save quebram juntos (wrap do pai não os separa)
              <Stack direction="row" spacing={1} alignItems="center">
                <Button color="error" sx={{ whiteSpace: "nowrap" }} onClick={cancelEdit}>
                  Cancel
                </Button>
                <Button
                  startIcon={<SaveIcon />}
                  variant="contained"
                  sx={{ whiteSpace: "nowrap" }}
                  onClick={() => setEditMode(false)}
                >
                  Save
                </Button>
              </Stack>
            ) : (
              <Button
                startIcon={<EditIcon />}
                variant="outlined"
                sx={{ whiteSpace: "nowrap" }}
                onClick={() => setEditMode(true)}
              >
                Edit
              </Button>
            ))}
          {/* documentos: exportar o draft (em edição) / baixar o relatório (fora) */}
          {canEdit && (
            <Button
              startIcon={<FileDownloadIcon />}
              variant="outlined"
              sx={{ whiteSpace: "nowrap" }}
              onClick={exportDraft}
            >
              Export draft (JSON)
            </Button>
          )}
          {!editMode && (
            <Button
              startIcon={<DownloadIcon />}
              variant="outlined"
              sx={{ whiteSpace: "nowrap" }}
              onClick={download}
            >
              Download report
            </Button>
          )}
        </Stack>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {githubError && (
        <Alert severity="warning" onClose={() => setGithubError("")}>
          Couldn't load GitHub repos, areas, or sizes ({githubError}). You can still type them.
        </Alert>
      )}
      {draft && (
        <Alert severity="info">
          This is a draft. Start the release when you're ready to begin.
        </Alert>
      )}
      {inExecution && release?.started_at && (
        <Alert severity="info">
          Started {new Date(release.started_at).toLocaleString()}.
          {editMode && " · Changes save as you go. Choose Save when you're done."}
        </Alert>
      )}
      {release?.status === "completed" && (
        <Alert severity="success">
          All activities are done.
          {editMode && " · Changes save as you go. Choose Save when you're done."}
        </Alert>
      )}
      {readonly && (
        <Alert severity="info">This release is archived. You can view it, but you can't make changes.</Alert>
      )}
      {draft && !(release?.steps || []).length && (
        <Alert severity="info">Add a step to start this draft.</Alert>
      )}
      {view === "kanban" ? (
        <StepBoard
          steps={release?.steps || []}
          activities={activities}
          onSelect={selectActivity}
          editable={canEdit}
          onMoveActivity={moveActivityDir}
          onDuplicateActivity={duplicateActivity}
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
        key={selected?.id}
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
        onDuplicate={duplicateActivity}
        onMove={moveActivity}
      />
      {canEdit && (
        <ActivityForm
          open={addOpen}
          steps={release?.steps || []}
          activities={activities}
          users={users}
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
      <Dialog open={deleteDraftOpen} onClose={() => setDeleteDraftOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Delete draft</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            "{release?.name}" and its steps, activities, and history will be deleted. This can't be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDraftOpen(false)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDeleteDraft}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>Delete step</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete "{deleteTarget?.label}"? You can delete a step only if it has no activities.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={confirmDeleteStep}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={renameOpen} onClose={() => setRenameOpen(false)} fullWidth maxWidth="xs">
        <form onSubmit={renameRelease}>
          <DialogTitle>Rename release</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField
                size="small"
                label="Name"
                value={renameName}
                onChange={(e) => setRenameName(e.target.value)}
                required
                fullWidth
                autoFocus
              />
              <Typography variant="body2" color="text.secondary">
                This name appears on GitHub issues and GLPI tickets. You can change it only while this is a draft.
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setRenameOpen(false)}>Cancel</Button>
            <Button type="submit" variant="contained" color="success">
              Rename
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <Dialog open={startOpen} onClose={() => setStartOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Start execution?</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2">
              {activities.length} activities · {withoutAssignee} without assignee · {withoutRepo} using default repo (idac_drd)
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Activities can start moving. You can still edit after you start.
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
