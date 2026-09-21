import { Position } from "@xyflow/react";
import { displayStatus } from "./activityStatus";

const CARD_WIDTH = 250; // largura do card de activity (ActivityFlowNode)
const LEVEL_WIDTH = CARD_WIDTH + 50; // passo por nível (eixo x): vão de 50px entre cards
const CARD_HEIGHT = 62; // altura real do card de activity (ActivityFlowNode)
export const NODE_GAP = CARD_HEIGHT + 28; // passo vertical por row: card + corredor
const PADDING = 12; // respiro da faixa acima/abaixo dos cards
const STEP_LABEL_WIDTH = 180; // largura do rótulo à esquerda de cada faixa
const STEP_LABEL_HEIGHT = 48; // altura real do rótulo
const STEP_LABEL_X = -(STEP_LABEL_WIDTH + 24);
const ROW_FIXPOINT_MAX = 20; // teto do fixpoint de corredores (monótono → converge muito antes)
const SMOOTHSTEP_OFFSET = 20; // offset padrão do getSmoothStepPath do React Flow

// Bump quando layout/fit mudam de semântica — invalida viewports antigos no sessionStorage.
export const DAG_VIEWPORT_VERSION = 3;

// depends_on pode vir undefined/null da API — nunca iterar cru.
function depsOf(a) {
  return Array.isArray(a?.depends_on) ? a.depends_on : [];
}

// Aresta longa (gap > 1): coloca o joelho vertical no VÃO entre a coluna do
// source e a próxima — fora de qualquer card. O segmento longo fica na Y do
// target (faixa do alvo), então arestas cross-step não atravessam steps do meio.
// Retorna undefined para gap ≤ 1 (o default 0.5 do RF já cai no vão adjacente).
export function longEdgeStepPosition(sourceLevel, targetLevel) {
  const gap = targetLevel - sourceLevel;
  if (gap <= 1) return undefined;
  const sourceGapped = sourceLevel * LEVEL_WIDTH + CARD_WIDTH + SMOOTHSTEP_OFFSET;
  const targetGapped = targetLevel * LEVEL_WIDTH - SMOOTHSTEP_OFFSET;
  const span = targetGapped - sourceGapped;
  if (span <= 0) return undefined;
  const gapCenter = sourceLevel * LEVEL_WIDTH + CARD_WIDTH + (LEVEL_WIDTH - CARD_WIDTH) / 2;
  const t = (gapCenter - sourceGapped) / span;
  return Math.min(0.95, Math.max(0.02, t));
}

// Linhas (eixo y) de um step: cada activity ganha um row index INTEIRO.
// Corredor: aresta longa reserva a row do ALVO nos níveis intermediários do
// step do alvo (é onde o smoothstep desenha o segmento horizontal longo, com
// o joelho no vão pós-source). Fixpoint monótono evita corredor stale.
function assignStepRows(stepId, stepActs, levels, byId, activities) {
  const order = [...stepActs].sort(
    (a, b) =>
      levels.get(a.id) - levels.get(b.id) ||
      (a.order ?? 0) - (b.order ?? 0) ||
      String(a.id).localeCompare(String(b.id)),
  );

  const place = (reservedByLevel) => {
    const rows = new Map();
    const occupied = new Map();
    const prefOf = (a) => {
      const parentRows = depsOf(a)
        .map((depId) => byId.get(depId))
        .filter((dep) => dep && dep.step === a.step && rows.has(dep.id))
        .map((dep) => rows.get(dep.id))
        .sort((x, y) => x - y);
      if (!parentRows.length) return 0;
      return parentRows[Math.floor((parentRows.length - 1) / 2)];
    };
    for (const a of order) {
      const level = levels.get(a.id);
      const occ = occupied.get(level) ?? new Set();
      const reserved = reservedByLevel?.get(level);
      let row = prefOf(a);
      while (occ.has(row) || reserved?.has(row)) row += 1;
      rows.set(a.id, row);
      occ.add(row);
      occupied.set(level, occ);
    }
    return rows;
  };

  // só a row do alvo (u): o segmento longo do smoothstep roda na Y do target
  const corridorsFrom = (rows) => {
    const reserved = new Map();
    const addRes = (level, row) => {
      if (!reserved.has(level)) reserved.set(level, new Set());
      reserved.get(level).add(row);
    };
    for (const u of activities) {
      if (u.step !== stepId) continue;
      const ru = rows.get(u.id);
      if (ru == null) continue;
      const lu = levels.get(u.id);
      for (const depId of depsOf(u)) {
        const v = byId.get(depId);
        if (!v) continue;
        const lv = levels.get(v.id);
        if (lu - lv <= 1) continue;
        for (let level = lv + 1; level < lu; level++) addRes(level, ru);
      }
    }
    return reserved;
  };

  const reserved = new Map();
  let rows = place(null);
  for (let iter = 0; iter < ROW_FIXPOINT_MAX; iter++) {
    const nextCorridors = corridorsFrom(rows);
    let grew = false;
    for (const [level, set] of nextCorridors) {
      if (!reserved.has(level)) reserved.set(level, new Set());
      const bucket = reserved.get(level);
      for (const row of set) {
        if (!bucket.has(row)) {
          bucket.add(row);
          grew = true;
        }
      }
    }
    const next = place(reserved);
    let changed = false;
    for (const [id, row] of next) {
      if (rows.get(id) !== row) {
        changed = true;
        break;
      }
    }
    rows = next;
    if (!changed && !grew) break;
  }
  return rows;
}

// Steps conhecidos + órfãos (activity.step fora da lista) — órfãos ganham faixa
// residual no fim para permanecerem clicáveis (y finito), sem derrubar o layout.
function layoutStepsFor(activities, steps) {
  const stepOrder = [...steps].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const known = new Set(stepOrder.map((s) => s.id));
  const orphanIds = [];
  for (const a of activities) {
    if (a.step != null && !known.has(a.step) && !orphanIds.includes(a.step)) {
      orphanIds.push(a.step);
    }
  }
  return [
    ...stepOrder,
    ...orphanIds.map((id) => ({
      id,
      label: `Unknown step (${id})`,
      order: Number.MAX_SAFE_INTEGER,
      color: "#757575",
    })),
  ];
}

// Layout por nível topológico HORIZONTAL: x = profundidade de dependências,
// y = step (faixas). Cada faixa cresce com o paralelismo do step.
export function computeDagState(activities, steps) {
  const layoutSteps = layoutStepsFor(activities, steps);
  const byId = new Map(activities.map((a) => [a.id, a]));

  const levels = new Map();
  const levelOf = (a) => {
    if (levels.has(a.id)) return levels.get(a.id);
    let lvl = 0;
    for (const depId of depsOf(a)) {
      const dep = byId.get(depId);
      if (dep) lvl = Math.max(lvl, levelOf(dep) + 1);
    }
    levels.set(a.id, lvl);
    return lvl;
  };
  activities.forEach(levelOf);
  const maxLevel = activities.length ? Math.max(0, ...activities.map((a) => levels.get(a.id))) : 0;

  const stepTop = new Map();
  const stepHeight = new Map();
  const yOf = new Map();
  let y = 0;
  for (const step of layoutSteps) {
    stepTop.set(step.id, y);
    const stepActs = activities.filter((a) => a.step === step.id);
    const rows = assignStepRows(step.id, stepActs, levels, byId, activities);
    const maxRow = rows.size ? Math.max(0, ...rows.values()) : 0;
    const height = 2 * PADDING + CARD_HEIGHT + maxRow * NODE_GAP;
    stepHeight.set(step.id, height);
    rows.forEach((row, id) => yOf.set(id, y + PADDING + row * NODE_GAP));
    y += height;
  }

  const graphWidth = (maxLevel + 1) * LEVEL_WIDTH;
  const graphHeight = y || 2 * PADDING + CARD_HEIGHT;

  const stepColor = new Map(layoutSteps.map((l) => [l.id, l.color || "#000099"]));

  const nodes = [
    ...layoutSteps.map((l, idx) => ({
      id: `band-${l.id}`,
      type: "stepBand",
      selectable: false,
      draggable: false,
      position: { x: 0, y: stepTop.get(l.id) },
      data: {
        width: graphWidth,
        height: stepHeight.get(l.id),
        alt: idx % 2 === 1,
      },
    })),
    ...activities.map((a) => ({
      id: String(a.id),
      type: "activity",
      zIndex: 1,
      position: { x: levels.get(a.id) * LEVEL_WIDTH, y: yOf.get(a.id) },
      data: { activity: a, level: levels.get(a.id), stepColor: stepColor.get(a.step) },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    })),
    ...layoutSteps.map((l) => {
      const stepActs = activities.filter((a) => a.step === l.id);
      return {
        id: `step-${l.id}`,
        type: "stepLabel",
        position: {
          x: STEP_LABEL_X,
          y: stepTop.get(l.id) + (stepHeight.get(l.id) - STEP_LABEL_HEIGHT) / 2,
        },
        data: {
          label: l.label,
          color: l.color,
          width: STEP_LABEL_WIDTH,
          done: stepActs.filter((a) => a.status === "done").length,
          total: stepActs.length,
        },
      };
    }),
  ];

  const edges = activities.flatMap((a) =>
    depsOf(a).flatMap((depId) => {
      if (!byId.has(depId)) return []; // dep fantasma: não cria aresta quebrada
      const sourceLevel = levels.get(depId);
      const targetLevel = levels.get(a.id);
      const edge = {
        id: `${depId}->${a.id}`,
        source: String(depId),
        target: String(a.id),
        targetStatus: displayStatus(a),
      };
      const stepPosition = longEdgeStepPosition(sourceLevel, targetLevel);
      if (stepPosition != null) edge.pathOptions = { stepPosition };
      return [edge];
    }),
  );

  return { nodes, edges, graphWidth, graphHeight, graphX: STEP_LABEL_X };
}
