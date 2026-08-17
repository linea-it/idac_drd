// Paleta curada de steps: 20 cores distinguíveis entre si e legíveis com
// texto branco (contraste >= 3:1 para texto bold). Sempre a mesma, em
// qualquer release ou template — sem cores livres.
export const STEP_COLORS = [
  { hex: "#2563EB", name: "Blue" },
  { hex: "#0284C7", name: "Sky" },
  { hex: "#0891B2", name: "Cyan" },
  { hex: "#0F766E", name: "Teal" },
  { hex: "#059669", name: "Emerald" },
  { hex: "#16A34A", name: "Green" },
  { hex: "#4D7C0F", name: "Olive" },
  { hex: "#A16207", name: "Ochre" },
  { hex: "#D97706", name: "Amber" },
  { hex: "#EA580C", name: "Orange" },
  { hex: "#DC2626", name: "Red" },
  { hex: "#BE123C", name: "Crimson" },
  { hex: "#DB2777", name: "Magenta" },
  { hex: "#C026D3", name: "Fuchsia" },
  { hex: "#9333EA", name: "Purple" },
  { hex: "#7C3AED", name: "Violet" },
  { hex: "#4F46E5", name: "Indigo" },
  { hex: "#31297F", name: "Brand indigo" },
  { hex: "#334155", name: "Slate" },
  { hex: "#6B7280", name: "Gray" },
];

// Cor padrão para um step novo: a primeira da paleta ainda não usada
// (a paleta se repete ciclicamente depois da 20º step).
export function defaultStepColor(steps) {
  const used = new Set((steps || []).map((l) => (l.color || "").toLowerCase()));
  return STEP_COLORS.find((c) => !used.has(c.hex.toLowerCase()))?.hex ?? STEP_COLORS[0].hex;
}
