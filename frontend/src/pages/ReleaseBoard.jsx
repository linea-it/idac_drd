import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import EditIcon from "@mui/icons-material/Edit";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
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
  Snackbar,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, appUrl } from "../api";
import { releaseStatusLabel } from "../activityStatus";
import { isFilterActive, matchesFilters } from "../activityFilters";
import { formatEffort } from "../timerUi";
import { downloadReport, downloadTextFile } from "../report";
import ActivityDagBoard from "../components/ActivityDagBoard";
import ActivityDrawer from "../components/ActivityDrawer";
import StepColorPicker from "../components/StepColorPicker";
import ActivityFilterBar from "../components/ActivityFilterBar";
import ActivityForm from "../components/ActivityForm";
import StepBoard from "../components/StepBoard";
import { defaultStepColor } from "../stepColors";

export default function ReleaseBoard({ releaseSlug, isStaff, isSuperuser = false, userEmail = "" }) {
  const [release, setRelease] = useState(null);
  const [activities, setActivities] = useState([]);
  const [users, setUsers] = useState([]);
  const [githubOptions, setGithubOptions] = useState({ repos: [], areas: [], sizes: [] });
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [view, setView] = useState("kanban");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [githubError, setGithubError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [bgNotice, setBgNotice] = useState(false);
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
  // filtros facetados (#25): vivem só aqui; troca Kanban↔DAG preserva
  const [filters, setFilters] = useState({ assignees: [], statuses: [], modes: [], areas: [] });
  const [hideUnmatched, setHideUnmatched] = useState(false);
  // modo de edição da execução: toggle. Alterações já gravam na hora.
  const [editMode, setEditMode] = useState(false);

  const doneCount = activities.filter((a) => a.status === "done").length;
  const draft = release?.status === "draft";
  const readonly = release?.status === "archived";
  const inExecution = release?.status === "active";
  const completed = release?.status === "completed";
  // draft é sempre editável; em active/completed a edição é o toggle Edit
  const canEdit = draft || ((inExecution || completed) && editMode);

  // single source of match: só matchesFilters decide o que bate com o filtro
  const filterActive = isFilterActive(filters);
  const matchedIds = useMemo(() => {
    const s = new Set();
    if (!filterActive) return s;
    for (const a of activities) if (matchesFilters(a, filters)) s.add(a.id);
    return s;
  }, [activities, filters, filterActive]);
  const matchedCount = filterActive ? matchedIds.size : activities.length;
  const playingNow = useMemo(() => {
    // banner só para o assignee logado (email), não para qualquer playing na release
    return (
      activities.find((a) => {
        if (!a.is_playing || !a.assignee?.email || !userEmail) return false;
        return (
          a.assignee.email.trim().toLowerCase() === userEmail.trim().toLowerCase()
        );
      }) || null
    );
  }, [activities, userEmail]);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError("");
    }
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
      if (!silent) setLoading(false);
    }
  }, [releaseSlug]);

  const loadOptions = useCallback(async () => {
    try {
      const opts = await api.get("/api/github/options/");
      setGithubOptions(opts);
      setGithubError(opts.error ? `GitHub: ${opts.error}` : "");
    } catch (err) {
      setGithubOptions({ repos: [], areas: [], sizes: [] });
      setGithubError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  function applyActivity(data) {
    if (!data || data.id == null) return;
    const activity = { ...data };
    delete activity.paused_activities;
    setActivities((prev) => prev.map((a) => (a.id === activity.id ? { ...a, ...activity } : a)));
    setSelected((prev) => (prev && prev.id === activity.id ? { ...prev, ...activity } : prev));
  }

  async function mutate(fn) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

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

  // mantém o drawer alinhado após load/play/pause
  useEffect(() => {
    setSelected((prev) => {
      if (!prev) return prev;
      return activities.find((a) => a.id === prev.id) || prev;
    });
  }, [activities]);

  async function saveActivity(payload) {
    await mutate(async () => {
      const data = await api.patch(`/api/activities/${selected.id}/`, payload);
      applyActivity(data);
      setFlash((f) => ({ id: selected.id, n: (f?.n ?? 0) + 1 }));
      load({ silent: true });
    });
  }

  async function playActivity(activity) {
    try {
      await mutate(async () => {
        const data = await api.post(`/api/activities/${activity.id}/play/`, {});
        const paused = data.paused_activities || [];
        applyActivity(data);
        if (paused.length) {
          const names = paused.map((p) => p.label).join(", ");
          setToast(`Paused: ${names}`);
        }
        setFlash((f) => ({ id: activity.id, n: (f?.n ?? 0) + 1 }));
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function pauseActivity(activity) {
    try {
      await mutate(async () => {
        const data = await api.post(`/api/activities/${activity.id}/pause/`, {});
        applyActivity(data);
        setFlash((f) => ({ id: activity.id, n: (f?.n ?? 0) + 1 }));
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function recordEffort(activity, minutes) {
    await mutate(async () => {
      const data = await api.post(`/api/activities/${activity.id}/effort/`, { minutes });
      applyActivity(data);
      setFlash((f) => ({ id: activity.id, n: (f?.n ?? 0) + 1 }));
      load({ silent: true });
    });
  }

  async function deleteActivity(activity) {
    await mutate(async () => {
      await api.del(`/api/activities/${activity.id}/`);
      setActivities((prev) => prev.filter((a) => a.id !== activity.id));
      closeDrawer();
      load({ silent: true });
    });
  }

  async function moveActivity(activity, payload) {
    await mutate(async () => {
      const data = await api.post(`/api/activities/${activity.id}/move/`, payload);
      applyActivity(data);
      load({ silent: true });
    });
  }

  async function duplicateActivity(activity) {
    try {
      await mutate(async () => {
        const copy = await api.post(`/api/activities/${activity.id}/duplicate/`, {});
        setActivities((prev) => [...prev, copy]);
        selectActivity(copy);
        load({ silent: true });
      });
    } catch (err) {
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
    try {
      await mutate(async () => {
        const created = await api.post(`/api/releases/${releaseSlug}/activities/`, payload);
        setActivities((prev) => [...prev, created]);
        load({ silent: true });
      });
    } catch (err) {
      throw err;
    }
  }

  async function confirmDeleteDraft() {
    try {
      await mutate(async () => {
        await api.del(`/api/releases/${releaseSlug}/`);
        window.location.href = document.querySelector(".navbar-brand")?.getAttribute("href") || appUrl("/");
      });
    } catch {
      setDeleteDraftOpen(false);
    }
  }

  async function archive() {
    try {
      await mutate(async () => {
        const data = await api.patch(`/api/releases/${releaseSlug}/`, { status: "archived" });
        setRelease(data);
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function unarchive() {
    try {
      await mutate(async () => {
        const data = await api.patch(`/api/releases/${releaseSlug}/`, { status: "active" });
        setRelease(data);
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
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

  async function saveStep(e) {
    e.preventDefault();
    try {
      await mutate(async () => {
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
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function confirmDeleteStep() {
    if (!deleteTarget) return;
    try {
      await mutate(async () => {
        await api.del(`/api/releases/${releaseSlug}/steps/${deleteTarget.id}/`);
        setDeleteTarget(null);
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function reorderStep(step, dir) {
    try {
      await mutate(async () => {
        await api.patch(`/api/releases/${releaseSlug}/steps/${step.id}/`, { direction: dir });
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function renameRelease(e) {
    e?.preventDefault();
    try {
      await mutate(async () => {
        const data = await api.patch(`/api/releases/${releaseSlug}/`, { name: renameName.trim() });
        setRelease(data);
        setRenameOpen(false);
        load({ silent: true });
      });
    } catch {
      /* banner */
    }
  }

  async function startExecution() {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    try {
      const data = await api.post(`/api/releases/${releaseSlug}/start/`);
      setRelease(data);
      setStartOpen(false);
      setBgNotice(true);
      load({ silent: true });
    } catch (err) {
      setError(err.message);
    } finally {
      pendingRef.current = false;
      setPending(false);
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
      {pending && <LinearProgress />}
      {bgNotice && (
        <Alert severity="info" onClose={() => setBgNotice(false)}>
          Creating GitHub issues and GLPI tickets in the background.
        </Alert>
      )}
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
          {/* estrutura: toggle de edição, depois adicionar step/atividade */}
          {(inExecution || completed) && (
            <ToggleButton
              size="small"
              value="edit"
              selected={editMode}
              onChange={() => setEditMode((on) => !on)}
              sx={{ whiteSpace: "nowrap", px: 1.5, textTransform: "none" }}
            >
              <EditIcon fontSize="small" sx={{ mr: 0.5 }} />
              Edit
            </ToggleButton>
          )}
          {(draft || editMode) && (
            <>
              <Button
                startIcon={<AddIcon />}
                variant="outlined"
                disabled={pending}
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
                variant="outlined"
                disabled={pending}
                sx={{ whiteSpace: "nowrap" }}
                onClick={() => setAddOpen(true)}
              >
                Add activity
              </Button>
            </>
          )}
          {/* ciclo de vida: só Start execution é preenchido */}
          {draft && isStaff && (
            <Button
              startIcon={<PlayArrowIcon />}
              variant="contained"
              color="success"
              disabled={pending}
              sx={{ whiteSpace: "nowrap" }}
              onClick={() => setStartOpen(true)}
            >
              Start execution
            </Button>
          )}
          {(inExecution || completed) && isStaff && (
            <Button variant="outlined" color="warning" disabled={pending} sx={{ whiteSpace: "nowrap" }} onClick={archive}>
              Archive
            </Button>
          )}
          {draft && (
            <Button
              startIcon={<DeleteIcon />}
              variant="outlined"
              color="error"
              disabled={pending}
              sx={{ whiteSpace: "nowrap" }}
              onClick={() => setDeleteDraftOpen(true)}
            >
              Delete draft
            </Button>
          )}
          {readonly && isStaff && (
            <Button variant="outlined" color="success" disabled={pending} sx={{ whiteSpace: "nowrap" }} onClick={unarchive}>
              Unarchive
            </Button>
          )}
          {/* documentos */}
          {canEdit && (
            <Button
              startIcon={<FileDownloadIcon />}
              variant="text"
              disabled={pending}
              sx={{ whiteSpace: "nowrap" }}
              onClick={exportDraft}
            >
              Export draft (JSON)
            </Button>
          )}
          {!editMode && (
            <Button
              startIcon={<DownloadIcon />}
              variant="text"
              disabled={pending}
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
      {playingNow && !draft && !readonly && (
        <Alert
          severity="success"
          icon={<PlayArrowIcon fontSize="inherit" />}
          action={
            <Button
              color="inherit"
              size="small"
              startIcon={<PauseIcon />}
              onClick={() => pauseActivity(playingNow)}
              disabled={pending}
            >
              Pause
            </Button>
          }
        >
          You&apos;re on: <strong>{playingNow.label}</strong>
          {formatEffort(playingNow.effort_seconds)
            ? ` · ${formatEffort(playingNow.effort_seconds)}`
            : ""}
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
        </Alert>
      )}
      {release?.status === "completed" && (
        <Alert severity="success">
          All activities are done.
        </Alert>
      )}
      {readonly && (
        <Alert severity="info">This release is archived. You can view it, but you can't make changes.</Alert>
      )}
      {draft && !(release?.steps || []).length && (
        <Alert severity="info">Add a step to start this draft.</Alert>
      )}
      <ActivityFilterBar
        activities={activities}
        filters={filters}
        onChange={setFilters}
        matched={matchedCount}
        total={activities.length}
        showHideToggle={view === "kanban"}
        hideUnmatched={hideUnmatched}
        onHideUnmatched={setHideUnmatched}
      />
      {view === "kanban" ? (
        <StepBoard
          steps={release?.steps || []}
          activities={activities}
          matchedIds={matchedIds}
          filterActive={filterActive}
          hideUnmatched={hideUnmatched}
          onSelect={selectActivity}
          editable={canEdit}
          onMoveActivity={moveActivityDir}
          pending={pending}
          onDuplicateActivity={duplicateActivity}
          onPlay={!draft && !readonly ? playActivity : undefined}
          onPause={!draft && !readonly ? pauseActivity : undefined}
          isSuperuser={isSuperuser}
          userEmail={userEmail}
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
          matchedIds={matchedIds}
          filterActive={filterActive}
          onSelect={selectActivity}
          selectedId={selected?.id ?? null}
          flash={flash}
          onPlay={!draft && !readonly ? playActivity : undefined}
          onPause={!draft && !readonly ? pauseActivity : undefined}
          pending={pending}
          isSuperuser={isSuperuser}
          userEmail={userEmail}
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
        onPlay={playActivity}
        onPause={pauseActivity}
        onRecordEffort={recordEffort}
        isSuperuser={isSuperuser}
        userEmail={userEmail}
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
            <Button onClick={() => setStepOpen(false)} disabled={pending}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={!stepLabel || pending}>
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
          <Button onClick={() => setDeleteDraftOpen(false)} disabled={pending}>Cancel</Button>
          <Button color="error" variant="contained" disabled={pending} onClick={confirmDeleteDraft}>
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
          <Button onClick={() => setDeleteTarget(null)} disabled={pending}>Cancel</Button>
          <Button color="error" variant="contained" disabled={pending} onClick={confirmDeleteStep}>
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
            <Button onClick={() => setRenameOpen(false)} disabled={pending}>Cancel</Button>
            <Button type="submit" variant="contained" color="success" disabled={pending}>
              Rename
            </Button>
          </DialogActions>
        </form>
      </Dialog>
      <Dialog open={startOpen} onClose={() => { if (!pending) setStartOpen(false); }} fullWidth maxWidth="xs">
        <DialogTitle>Start execution?</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <Typography variant="body2">
              {activities.length} activities · {withoutAssignee} without assignee · {withoutRepo} using default repo (idac_drd)
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Activities can start moving. You can still edit after you start.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartOpen(false)} disabled={pending}>Cancel</Button>
          <Button variant="contained" color="success" onClick={startExecution} disabled={pending}>
            {pending ? "Starting…" : "Start execution"}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={4000}
        onClose={() => setToast("")}
        message={toast}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Stack>
  );
}
