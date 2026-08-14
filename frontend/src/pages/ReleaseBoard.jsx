import AddIcon from "@mui/icons-material/Add";
import DownloadIcon from "@mui/icons-material/Download";
import {
  Alert,
  Button,
  Chip,
  LinearProgress,
  Skeleton,
  Stack,
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
import StageForm from "../components/StageForm";
import SwimlaneBoard from "../components/SwimlaneBoard";

export default function ReleaseBoard({ releaseSlug }) {
  const [release, setRelease] = useState(null);
  const [activities, setActivities] = useState([]);
  const [users, setUsers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [view, setView] = useState("kanban");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // anel de destaque no DAG: { id do stage editado, n incrementa a cada save }
  const [flash, setFlash] = useState(null);

  const doneCount = activities.filter((a) => a.status === "done").length;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [rel, acts, us] = await Promise.all([
        api.get(`/api/releases/${releaseSlug}/`),
        api.get(`/api/releases/${releaseSlug}/activities/`),
        api.get("/api/users/"),
      ]);
      setRelease(rel);
      setActivities(acts);
      setUsers(us);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [releaseSlug]);

  useEffect(() => {
    load();
  }, [load]);

  const readonly = release?.status === "archived";

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
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            label={releaseStatusLabel(release?.status)}
            color={
              release?.status === "active"
                ? "info"
                : release?.status === "completed"
                  ? "success"
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
          <ToggleButtonGroup
            size="small"
            exclusive
            value={view}
            onChange={(_, v) => v && setView(v)}
          >
            <ToggleButton value="kanban">Kanban</ToggleButton>
            <ToggleButton value="dag">DAG</ToggleButton>
          </ToggleButtonGroup>
          {!readonly ? (
            <>
              <Button startIcon={<AddIcon />} variant="contained" onClick={() => setAddOpen(true)}>
                Add stage
              </Button>
              <Button variant="outlined" color="warning" onClick={archive}>
                Archive
              </Button>
            </>
          ) : (
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
      {readonly && <Alert severity="info">This release is archived (read-only).</Alert>}
      {view === "kanban" ? (
        <SwimlaneBoard
          lanes={release?.lanes || []}
          activities={activities}
          onSelect={selectActivity}
        />
      ) : (
        <ActivityDagBoard
          lanes={release?.lanes || []}
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
        lanes={release?.lanes || []}
        activities={activities}
        readonly={readonly}
        onClose={closeDrawer}
        onSave={saveActivity}
        onDelete={deleteActivity}
        onMove={moveActivity}
      />
      <StageForm
        open={addOpen}
        lanes={release?.lanes || []}
        activities={activities}
        onClose={() => setAddOpen(false)}
        onSubmit={createActivity}
      />
    </Stack>
  );
}
