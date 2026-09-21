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

// Linhas (eixo y) de um step: cada activity ganha um row index INTEIRO — sem
// centrar grupos isolados. Nós do mesmo nível dividem rows (paralelos espalham
// na vertical); dependências alinhadas tentam ficar na MESMA row (aresta reta).
// Aresta longa (gap de nível > 1): o smoothstep desenha o segmento horizontal
// na row do source do handle até o meio do vão e na row do target do meio até o
// handle — nos níveis intermediários essas rows ficam RESERVADAS (corredor) e
// quem cair nelas é empurrado para a próxima livre (#28).
//
// Fixpoint monótono: corredores dependem das rows finais dos endpoints; se um
// alvo sobe de row no passe seguinte, a reserva antiga fica stale. Acumulamos
// reservas (só crescem) e recolocamos até estabilizar — rows só sobem, então
// termina em ≤ N iterações.
function assignStepRows(stepId, stepActs, levels, byId, activities) {
  // níveis da esquerda para a direita; dentro do nível, por order/id (determinístico)
  const order = [...stepActs].sort(
    (a, b) =>
      levels.get(a.id) - levels.get(b.id) ||
      (a.order ?? 0) - (b.order ?? 0) ||
      String(a.id).localeCompare(String(b.id)),
  );

  const place = (reservedByLevel) => {
    const rows = new Map(); // activity id -> row index
    const occupied = new Map(); // nível -> Set de rows ocupadas naquele nível
    // preferência de row: mediana inferior (barycenter) das rows dos pais JÁ
    // POSICIONADOS no mesmo step; sem pais no step, 0 (faixas compartilham a
    // mesma grade de rows, então cadeias entre steps seguem retas também)
    const prefOf = (a) => {
      const parentRows = a.depends_on
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
      while (occ.has(row) || reserved?.has(row)) row += 1; // ocupada/reservada → empurra
      rows.set(a.id, row);
      occ.add(row);
      occupied.set(level, occ);
    }
    return rows;
  };

  // corredores a partir das rows atuais: por aresta u←v (depends_on) com gap > 1,
  // reserva a row de cada endpoint nos níveis intermediários DO STEP DO ENDPOINT.
  // Com gap PAR o segmento vertical cai na coluna do meio — reserva o intervalo.
  const corridorsFrom = (rows) => {
    const reserved = new Map();
    const addRes = (level, row) => {
      if (!reserved.has(level)) reserved.set(level, new Set());
      reserved.get(level).add(row);
    };
    for (const u of activities) {
      for (const depId of u.depends_on) {
        const v = byId.get(depId);
        if (!v) continue;
        const lu = levels.get(u.id);
        const lv = levels.get(v.id);
        const gap = lu - lv;
        if (gap <= 1) continue;
        const ru = u.step === stepId ? rows.get(u.id) : null;
        const rv = v.step === stepId ? rows.get(v.id) : null;
        if (ru == null && rv == null) continue;
        for (let level = lv + 1; level < lu; level++) {
          if (rv != null) addRes(level, rv);
          if (ru != null) addRes(level, ru);
        }
        if (ru != null && rv != null && gap % 2 === 0) {
          const mid = lv + gap / 2;
          const lo = Math.min(ru, rv);
          const hi = Math.max(ru, rv);
          for (let row = lo; row <= hi; row++) addRes(mid, row);
        }
      }
    }
    return reserved;
  };

  // fixpoint: reservas acumuladas (monótonas) + rows só sobem → converge
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

// Layout por nível topológico HORIZONTAL: x = profundidade de dependências (toda
// aresta aponta para a direita por construção — sem loops nem setas "para trás"),
// y = step (faixas horizontais, como no Kanban). Cada faixa tem um rótulo à
// esquerda, fundo zebrado e os nós distribuídos em rows; a altura da faixa
// cresce com o paralelismo do step.
export function computeDagState(activities, steps) {
  const stepOrder = [...steps].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const byId = new Map(activities.map((a) => [a.id, a]));

  // nível topológico: profundidade máxima de deps (é o x do layout e o delay do reveal)
  const levels = new Map();
  const levelOf = (a) => {
    if (levels.has(a.id)) return levels.get(a.id);
    let lvl = 0;
    for (const depId of a.depends_on) {
      const dep = byId.get(depId);
      if (dep) lvl = Math.max(lvl, levelOf(dep) + 1);
    }
    levels.set(a.id, lvl);
    return lvl;
  };
  activities.forEach(levelOf);
  const maxLevel = Math.max(0, ...activities.map((a) => levels.get(a.id)));

  // y por step: faixas empilhadas. Altura = padding + cards + corredores entre
  // rows + padding — sem o corredor "fantasma" após o último card (antes a
  // fórmula (maxRow+1)*NODE_GAP deixava a faixa assimétrica e inchada com 1 card)
  const stepTop = new Map();
  const stepHeight = new Map();
  const yOf = new Map();
  let y = 0;
  for (const step of stepOrder) {
    stepTop.set(step.id, y);
    const stepActs = activities.filter((a) => a.step === step.id);
    const rows = assignStepRows(step.id, stepActs, levels, byId, activities);
    const maxRow = Math.max(0, ...rows.values());
    const height = 2 * PADDING + CARD_HEIGHT + maxRow * NODE_GAP;
    stepHeight.set(step.id, height);
    rows.forEach((row, id) => yOf.set(id, y + PADDING + row * NODE_GAP));
    y += height;
  }

  const graphWidth = (maxLevel + 1) * LEVEL_WIDTH;
  // dimensões totais do grafo (usadas para o fit-height na abertura do board)
  const graphHeight = y; // soma das alturas de todas as faixas

  const stepColor = new Map(stepOrder.map((l) => [l.id, l.color || "#000099"]));

  const nodes = [
    // banda de cada faixa: largura total do grafo, fundo zebrado (visível em
    // qualquer zoom) — a altura acompanha o paralelismo do step
    ...stepOrder.map((l, idx) => ({
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
    ...stepOrder.map((l) => {
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
    a.depends_on.map((depId) => ({
      id: `${depId}->${a.id}`,
      source: String(depId),
      target: String(a.id),
      // a aresta é pintada pelo status EFETIVO do alvo (o dependente) — ver edgeStyles.js
      targetStatus: displayStatus(a),
    })),
  );

  return { nodes, edges, graphWidth, graphHeight, graphX: STEP_LABEL_X };
}
