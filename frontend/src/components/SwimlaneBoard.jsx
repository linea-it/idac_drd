import LockIcon from "@mui/icons-material/Lock";
import { Box, Card, CardActionArea, CardContent, Chip, Stack, Typography } from "@mui/material";
import { displayStatus, statusLabel } from "../activityStatus";
import { statusColors } from "../statusColors";

export default function SwimlaneBoard({ lanes, activities, onSelect }) {
  return (
    <Box
      sx={{
        display: "flex",
        gap: 2,
        overflowX: "auto",
        pb: 2,
        alignItems: "flex-start",
      }}
    >
      {lanes.map((lane) => {
        const laneActs = activities
          .filter((a) => a.lane === lane.id)
          .sort((a, b) => a.order - b.order);
        return (
          <Box key={lane.id} sx={{ minWidth: 260, maxWidth: 280, flex: "0 0 auto" }}>
            <Box
              sx={{
                bgcolor: lane.color || "#0989cb",
                color: "#fff",
                px: 1.5,
                py: 1,
                borderRadius: 1,
                mb: 1,
              }}
            >
              <Typography variant="subtitle2" fontWeight={700}>
                {lane.label}
              </Typography>
              <Typography variant="caption">
                {laneActs.filter((a) => a.status === "done").length}/{laneActs.length} done
              </Typography>
            </Box>
            <Stack spacing={1}>
              {laneActs.map((activity) => (
                <Card
                  key={activity.id}
                  variant="outlined"
                  sx={{
                    opacity: activity.locked ? 0.7 : 1,
                    borderColor:
                      displayStatus(activity) === "blocked" ? "warning.main" : "divider",
                  }}
                >
                  <CardActionArea onClick={() => onSelect(activity)}>
                    <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                      <Stack spacing={1}>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          {activity.locked && <LockIcon fontSize="small" color="disabled" />}
                          <Typography variant="body2" fontWeight={600}>
                            {activity.label}
                          </Typography>
                        </Stack>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          <Chip
                            size="small"
                            label={statusLabel(displayStatus(activity))}
                            color={statusColors[displayStatus(activity)]}
                          />
                          <Chip
                            size="small"
                            label={activity.mode === "nifi" ? "NiFi" : "Manual"}
                            color={activity.mode === "nifi" ? "info" : "default"}
                          />
                          {activity.assignee && (
                            <Chip
                              size="small"
                              variant="outlined"
                              label={activity.assignee.name || activity.assignee.username}
                            />
                          )}
                        </Stack>
                      </Stack>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
          </Box>
        );
      })}
    </Box>
  );
}
