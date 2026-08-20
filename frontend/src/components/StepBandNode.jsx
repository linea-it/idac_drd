import { Box } from "@mui/material";

// Banda de fundo de cada faixa horizontal: largura total do grafo, com fundo
// zebrado (alt) — o contraste entre faixas substitui o divisor fino.
export default function StepBandNode({ data }) {
  return (
    <Box
      sx={{
        width: data.width,
        height: data.height,
        bgcolor: data.alt ? "action.hover" : "transparent",
        // a banda cobre a faixa inteira; sem isso o hover do card perde o
        // ponteiro para a banda a cada re-render e o grafo pisca
        pointerEvents: "none",
      }}
    />
  );
}
