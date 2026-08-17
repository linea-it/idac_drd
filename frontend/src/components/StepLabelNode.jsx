import { Box, Typography } from "@mui/material";

// Cabeçalho de coluna com a largura real da faixa (data.width): todas as activities
// desse step ficam rigorosamente dentro do limite visual da coluna.
export default function StepLabelNode({ data }) {
  return (
    <Box
      sx={{
        width: data.width,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        px: 1.5,
        py: 0.5,
        textAlign: "left",
      }}
    >
      <Typography
        variant="subtitle2"
        fontWeight={700}
        sx={{ color: data.color || "#0989cb", whiteSpace: "nowrap" }}
      >
        {data.label}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {data.done}/{data.total} done
      </Typography>
    </Box>
  );
}
