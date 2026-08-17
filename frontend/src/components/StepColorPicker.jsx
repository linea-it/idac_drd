import CheckIcon from "@mui/icons-material/Check";
import { Box, Tooltip } from "@mui/material";
import { STEP_COLORS } from "../stepColors";

// Grade de swatches da paleta fixa (20 cores). Um step tem cor da paleta,
// nunca cor livre.
export default function StepColorPicker({ value, onChange }) {
  return (
    <Box
      role="radiogroup"
      aria-label="Step color"
      sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(26px, 1fr))", gap: 0.75 }}
    >
      {STEP_COLORS.map((c) => {
        const selected = c.hex.toLowerCase() === (value || "").toLowerCase();
        return (
          <Tooltip key={c.hex} title={c.name} arrow>
            <Box
              component="button"
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={c.name}
              onClick={() => onChange(c.hex)}
              sx={{
                width: 26,
                height: 26,
                borderRadius: "50%",
                bgcolor: c.hex,
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                outline: selected ? `2px solid ${c.hex}` : "none",
                outlineOffset: 2,
                boxShadow: selected ? "0 0 0 3px rgba(0,0,0,0.08)" : "none",
                transition: "transform 120ms ease",
                "&:hover": { transform: "scale(1.1)" },
              }}
            >
              {selected && <CheckIcon sx={{ color: "#fff", fontSize: 15 }} />}
            </Box>
          </Tooltip>
        );
      })}
    </Box>
  );
}
