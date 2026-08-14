import { Alert, Button, Card, CardContent, Stack, Typography } from "@mui/material";

export default function AuthGate({ loginUrl }) {
  return (
    <Card elevation={2} sx={{ maxWidth: 520, mx: "auto", mt: 6 }}>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h5">WKFW Dashboard</Typography>
          <Typography variant="body2" color="text.secondary">
            Sign in to track data release workflows, assign activities, and inspect bottlenecks.
          </Typography>
          <Alert severity="info">Authentication required.</Alert>
          <Button variant="contained" href={loginUrl}>
            Sign In
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
