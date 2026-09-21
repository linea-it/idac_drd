import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import WavingHandOutlinedIcon from "@mui/icons-material/WavingHandOutlined";
import { Box, Tooltip } from "@mui/material";

const MODES = {
  nifi: {
    label: "NiFi",
    color: "info.main",
    Icon: SmartToyOutlinedIcon,
  },
  manual: {
    label: "Manual",
    // Matches MUI Chip outlined "default" border/text tone
    color: "action.active",
    Icon: WavingHandOutlinedIcon,
  },
};

/**
 * Icon-only mode indicator (NiFi / Manual). Label is exposed via Tooltip + aria-label.
 * Uses a focusable Box instead of an empty MUI Chip to avoid fighting Chip label padding.
 */
export default function ModeChip({ mode, size = "medium", sx }) {
  const { label, color, Icon } = MODES[mode] ?? MODES.manual;
  // Match MUI Chip size heights (small=24, medium=32)
  const height = size === "small" ? 24 : 32;

  return (
    <Tooltip title={label} arrow>
      <Box
        component="span"
        tabIndex={0}
        role="img"
        aria-label={label}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          boxSizing: "border-box",
          height,
          px: "4px",
          border: 1,
          borderColor: color,
          borderRadius: 1, // theme.shape.borderRadius (8px)
          color,
          bgcolor: "background.paper",
          outline: "none",
          "&:focus-visible": {
            boxShadow: (theme) => `0 0 0 2px ${theme.palette.primary.main}`,
          },
          ...sx,
        }}
      >
        <Icon sx={{ fontSize: 14 }} />
      </Box>
    </Tooltip>
  );
}
