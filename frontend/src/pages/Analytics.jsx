import {
  Alert,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";
import BottleneckChart from "../components/BottleneckChart";

export default function Analytics() {
  const [releases, setReleases] = useState([]);
  const [release, setRelease] = useState("");
  const [compare, setCompare] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/releases/")
      .then((list) => {
        setReleases(list);
        if (list[0]) setRelease(list[0].slug);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!release) return;
    const qs = new URLSearchParams({ release });
    if (compare) qs.set("compare", compare);
    api
      .get(`/api/analytics/bottlenecks/?${qs}`)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [release, compare]);

  return (
    <Stack spacing={3}>
      <div>
        <Typography variant="h5">Analytics</Typography>
        <Typography variant="body2" color="text.secondary">
          Duration and bottlenecks per activity, with optional release comparison.
        </Typography>
      </div>
      {error && <Alert severity="error">{error}</Alert>}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Release</InputLabel>
          <Select label="Release" value={release} onChange={(e) => setRelease(e.target.value)}>
            {releases.map((r) => (
              <MenuItem key={r.slug} value={r.slug}>
                {r.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Compare</InputLabel>
          <Select label="Compare" value={compare} onChange={(e) => setCompare(e.target.value)}>
            <MenuItem value="">None</MenuItem>
            {releases
              .filter((r) => r.slug !== release)
              .map((r) => (
                <MenuItem key={r.slug} value={r.slug}>
                  {r.name}
                </MenuItem>
              ))}
          </Select>
        </FormControl>
      </Stack>
      {data?.primary?.bottleneck && (
        <Alert severity="warning">
          <strong>{data.primary.bottleneck.label}</strong> is taking the longest (
          {Math.round(data.primary.bottleneck.duration_seconds / 60)} min).
        </Alert>
      )}
      <Card elevation={2}>
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            Longest completed activities
          </Typography>
          <BottleneckChart rows={data?.by_key || []} />
        </CardContent>
      </Card>
    </Stack>
  );
}
