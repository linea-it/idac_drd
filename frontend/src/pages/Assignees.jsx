import {
  Alert,
  Button,
  Card,
  CardContent,
  LinearProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Assignees({ isStaff }) {
  const [users, setUsers] = useState([]);
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const list = await api.get("/api/users/");
      setUsers(list);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createUser(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      await api.post("/api/users/", {
        username,
        name,
        email,
        password,
      });
      setUsername("");
      setName("");
      setEmail("");
      setPassword("");
      setInfo("User created.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Stack spacing={3}>
      <div>
        <Typography variant="h5">Assignees</Typography>
        <Typography variant="body2" color="text.secondary">
          Users available to assign to activities.
        </Typography>
      </div>
      {!isStaff && (
        <Alert severity="info">View only. Staff permission required to create users.</Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      {info && <Alert severity="success">{info}</Alert>}
      {loading && <LinearProgress />}
      <Card elevation={2}>
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            Users ({users.length})
          </Typography>
          <Stack spacing={1}>
            {users.map((u) => (
              <Stack key={u.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2" fontWeight={600}>
                  {u.username}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {u.name || "—"} · {u.email || "—"}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </CardContent>
      </Card>
      {isStaff && (
        <Card elevation={2}>
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              Create user
            </Typography>
            <Stack component="form" onSubmit={createUser} spacing={2}>
              <TextField
                size="small"
                label="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
              <TextField
                size="small"
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <TextField
                size="small"
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <TextField
                size="small"
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Button type="submit" variant="contained" disabled={!username || !password}>
                Create user
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
