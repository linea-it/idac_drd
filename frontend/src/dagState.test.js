import { describe, expect, it } from "vitest";
import {
  NODE_GAP,
  DAG_VIEWPORT_VERSION,
  computeDagState,
  longEdgeStepPosition,
} from "./dagState";

const CARD_W = 250;
const CARD_H = 62;
const LEVEL_WIDTH = 300;
const OFFSET = 20;

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

function segHit(sx1, sy1, sx2, sy2, rx, ry, rw, rh) {
  for (let i = 0; i <= 80; i++) {
    const x = sx1 + ((sx2 - sx1) * i) / 80;
    const y = sy1 + ((sy2 - sy1) * i) / 80;
    if (x > rx + 0.5 && x < rx + rw - 0.5 && y > ry + 0.5 && y < ry + rh - 0.5) return true;
  }
  return false;
}

// Colisão geométrica respeitando pathOptions.stepPosition (mesmo modelo do RF)
function collisions(activities, steps) {
  const { nodes, edges } = computeDagState(activities, steps);
  const pos = new Map(nodes.filter((n) => n.type === "activity").map((n) => [n.id, n.position]));
  const stepPosById = new Map(edges.map((e) => [e.id, e.pathOptions?.stepPosition ?? 0.5]));
  const hits = [];
  for (const e of edges) {
    const p = pos.get(e.source);
    const t = pos.get(e.target);
    if (!p || t?.y == null || p.y == null) continue;
    const sx = p.x + CARD_W;
    const sy = p.y + CARD_H / 2;
    const tx = t.x;
    const ty = t.y + CARD_H / 2;
    const tPos = stepPosById.get(e.id) ?? 0.5;
    const cx = sx + OFFSET + (tx - OFFSET - (sx + OFFSET)) * tPos;
    for (const [oid, o] of pos) {
      if (oid === e.source || oid === e.target || o.y == null) continue;
      if (
        segHit(sx, sy, cx, sy, o.x, o.y, CARD_W, CARD_H) ||
        segHit(cx, sy, cx, ty, o.x, o.y, CARD_W, CARD_H) ||
        segHit(cx, ty, tx, ty, o.x, o.y, CARD_W, CARD_H)
      ) {
        hits.push(`${e.id} x ${oid}`);
      }
    }
  }
  return hits;
}

describe("computeDagState — layout Y por rows (#28)", () => {
  it("aresta longa A→C não atravessa o card B do nível intermediário", () => {
    const activities = [
      act({ id: "A", step: 1, order: 0 }),
      act({ id: "B", step: 1, order: 1, depends_on: ["A"] }),
      act({ id: "C", step: 1, order: 2, depends_on: ["A", "B"] }),
    ];
    const { nodes } = computeDagState(activities, [step()]);
    const pos = positions(nodes);
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
    expect(band.data.height).toBeGreaterThan(NODE_GAP);
  });

  it("1 card: faixa justa e padding simétrico acima/abaixo", () => {
    const { nodes } = computeDagState([act({ id: "A" })], [step()]);
    const band = nodes.find((n) => n.id === "band-1");
    const card = nodes.find((n) => n.id === "A");
    const top = card.position.y - band.position.y;
    const bottom = band.position.y + band.data.height - (card.position.y + CARD_H);
    expect(top).toBe(bottom);
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

describe("cross-step + pathOptions", () => {
  it("longEdgeStepPosition coloca o joelho no vão pós-source (fora do card)", () => {
    const t = longEdgeStepPosition(0, 2);
    expect(t).toBeGreaterThan(0);
    expect(t).toBeLessThan(0.5); // joelho perto do source, no vão 0→1
    const sourceGapped = CARD_W + OFFSET;
    const targetGapped = 2 * LEVEL_WIDTH - OFFSET;
    const cx = sourceGapped + (targetGapped - sourceGapped) * t;
    // vão entre coluna 0 (…250) e coluna 1 (300…): 250 < cx < 300
    expect(cx).toBeGreaterThan(CARD_W);
    expect(cx).toBeLessThan(LEVEL_WIDTH);
  });

  it("aresta longa cross-step não atravessa cards do step intermediário", () => {
    const steps = [step({ id: 1, order: 0 }), step({ id: 2, order: 1 }), step({ id: 3, order: 2 })];
    const activities = [
      act({ id: "A", step: 1, order: 0 }),
      act({ id: "M", step: 2, order: 0, depends_on: ["A"] }),
      act({ id: "X", step: 2, order: 1, depends_on: ["A"] }),
      act({ id: "D", step: 3, order: 0, depends_on: ["A", "M"] }), // A→D gap 2
    ];
    const { edges } = computeDagState(activities, steps);
    const longEdge = edges.find((e) => e.id === "A->D");
    expect(longEdge.pathOptions?.stepPosition).toBeDefined();
    expect(collisions(activities, steps)).toEqual([]);
  });
});

describe("dados inválidos (defensivo)", () => {
  it("depends_on undefined não quebra e vira lista vazia", () => {
    expect(() => computeDagState([act({ id: "A", depends_on: undefined })], [step()])).not.toThrow();
    const { edges, nodes } = computeDagState([act({ id: "A", depends_on: null })], [step()]);
    expect(edges).toEqual([]);
    expect(nodes.find((n) => n.id === "A").position.y).toBeTypeOf("number");
  });

  it("dep fantasma (id inexistente) não cria aresta", () => {
    const { edges } = computeDagState([act({ id: "A", depends_on: [999] })], [step()]);
    expect(edges).toEqual([]);
  });

  it("activity com step órfão ganha y finito e faixa residual", () => {
    const { nodes } = computeDagState([act({ id: "A", step: 99 })], [step({ id: 1 })]);
    const card = nodes.find((n) => n.id === "A");
    const band = nodes.find((n) => n.id === "band-99");
    const label = nodes.find((n) => n.id === "step-99");
    expect(card.position.y).toBeTypeOf("number");
    expect(Number.isFinite(card.position.y)).toBe(true);
    expect(band).toBeTruthy();
    expect(label.data.label).toContain("99");
  });
});

describe("viewport versioning", () => {
  it("DAG_VIEWPORT_VERSION é inteiro positivo (bump invalida sessionStorage)", () => {
    expect(Number.isInteger(DAG_VIEWPORT_VERSION)).toBe(true);
    expect(DAG_VIEWPORT_VERSION).toBeGreaterThan(0);
  });
});
