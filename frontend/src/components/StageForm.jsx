import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  InputLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";

export default function StageForm({ open, lanes, activities, onClose, onSubmit }) {
  const [label, setLabel] = useState("");
  const [laneId, setLaneId] = useState(lanes[0]?.id || "");
  const [afterId, setAfterId] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState("manual");
  const [saving, setSaving] = useState(false);

  const laneActivities = activities.filter((a) => a.lane === Number(laneId) || a.lane === laneId);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({
        label,
        lane_id: Number(laneId),
        after_id: afterId ? Number(afterId) : null,
        description,
        mode,
      });
      setLabel("");
      setDescription("");
      setAfterId("");
      setMode("manual");
      onClose();
    } finally {
      setSaving(false);
    }
  }

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
              <InputLabel>Lane</InputLabel>
              <Select label="Lane" value={laneId} onChange={(e) => setLaneId(e.target.value)}>
                {lanes.map((l) => (
                  <MenuItem key={l.id} value={l.id}>
                    {l.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>After</InputLabel>
              <Select label="After" value={afterId} onChange={(e) => setAfterId(e.target.value)}>
                <MenuItem value="">(none / start of lane)</MenuItem>
                {laneActivities.map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    {a.label}
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
            <TextField
              label="Description"
              size="small"
              fullWidth
              multiline
              minRows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
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
