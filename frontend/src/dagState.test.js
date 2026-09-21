import { describe, expect, it } from "vitest";
import { NODE_GAP, computeDagState } from "./dagState";

// fixture mínima de activity (campos usados por computeDagState/displayStatus)
const act = (over = {}) => ({
  id: "a",
  label: "A",
  status: "todo",
  prerequisites_met: true,
  blocked_reason: "",
  step: 1,
  order: 0,
  depends_on: [],
  ...over,
});

const step = (over = {}) => ({ id: 1, label: "Step 1", order: 0, color: "#000099", ...over });

const positions = (nodes) => new Map(nodes.map((n) => [n.id, n.position]));

describe("computeDagState — layout Y por rows (#28)", () => {
  it("aresta longa A→C não atravessa o card B do nível intermediário", () => {
    // B fica no nível 1, entre A (0) e C (2): C depende de A e de B — a aresta
    // A→C pula o nível de B e precisa de um corredor livre
    const activities = [
      act({ id: "A", step: 1, order: 0 }),
      act({ id: "B", step: 1, order: 1, depends_on: ["A"] }),
      act({ id: "C", step: 1, order: 2, depends_on: ["A", "B"] }),
    ];
    const { nodes } = computeDagState(activities, [step()]);
    const pos = positions(nodes);
    // A e C alinhados na mesma row (aresta reta) e B fora do corredor
    expect(pos.get("A").y).toBe(pos.get("C").y);
    expect(pos.get("B").y).not.toBe(pos.get("A").y);
    expect(pos.get("B").y).not.toBe(pos.get("C").y);
  });

  it("paralelos no mesmo step+nível ocupam rows distintas e a banda cresce", () => {
    const activities = [act({ id: "A", step: 1, order: 0 }), act({ id: "B", step: 1, order: 1 })];
    const { nodes } = computeDagState(activities, [step()]);
    const pos = positions(nodes);
    expect(pos.get("B").y).not.toBe(pos.get("A").y);
    expect(Math.abs(pos.get("B").y - pos.get("A").y)).toBe(NODE_GAP);
    const band = nodes.find((n) => n.id === "band-1");
    // 2 cards + corredor entre eles + padding simétrico (não 2*NODE_GAP)
    expect(band.data.height).toBeGreaterThan(NODE_GAP);
  });

  it("1 card: faixa justa e padding simétrico acima/abaixo", () => {
    const { nodes } = computeDagState([act({ id: "A" })], [step()]);
    const band = nodes.find((n) => n.id === "band-1");
    const card = nodes.find((n) => n.id === "A");
    const CARD_H = 62;
    const top = card.position.y - band.position.y;
    const bottom = band.position.y + band.data.height - (card.position.y + CARD_H);
    expect(top).toBe(bottom);
    // sem o corredor fantasma: faixa bem menor que 2*NODE_GAP
    expect(band.data.height).toBeLessThan(2 * NODE_GAP);
  });

  it("steps distintos empilham as faixas sem sobrepor stepTop", () => {
    const steps = [step({ id: 1, order: 0 }), step({ id: 2, order: 1 })];
    const activities = [act({ id: "A", step: 1 }), act({ id: "B", step: 2, depends_on: ["A"] })];
    const { nodes } = computeDagState(activities, steps);
    const band1 = nodes.find((n) => n.id === "band-1");
    const band2 = nodes.find((n) => n.id === "band-2");
    expect(band2.position.y).toBe(band1.position.y + band1.data.height);
  });
});
