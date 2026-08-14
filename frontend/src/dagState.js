import { Position } from "@xyflow/react";
import { displayStatus } from "./activityStatus";

const CARD_WIDTH = 250; // largura do card de activity (ActivityFlowNode)
const LEVEL_WIDTH = CARD_WIDTH + 50; // passo por nível (eixo x): vão de 50px entre cards
const NODE_STEP = 76; // passo vertical dos nós de um grupo (mesma lane, mesmo nível)
const CARD_HEIGHT = 62; // altura real do card de activity (ActivityFlowNode)
const LANE_LABEL_WIDTH = 180; // largura do rótulo à esquerda de cada faixa
const LANE_LABEL_HEIGHT = 48; // altura real do rótulo
const LANE_LABEL_X = -(LANE_LABEL_WIDTH + 24);

// Layout por nível topológico HORIZONTAL: x = profundidade de dependências (toda
// aresta aponta para a direita por construção — sem loops nem setas "para trás"),
// y = lane (faixas horizontais, como no Kanban). Cada faixa tem um rótulo à
// esquerda, um divisor fino na borda inferior e os nós centralizados na faixa.
export function computeDagState(activities, lanes) {
  const laneOrder = [...lanes].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
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

  // grupos: nós da mesma lane no mesmo nível colidem em y — a faixa acomoda o
  // maior grupo, e cada grupo é centralizado dentro da faixa
  const groupSizes = new Map();
  activities.forEach((a) => {
    const k = `${a.lane}:${levels.get(a.id)}`;
    groupSizes.set(k, (groupSizes.get(k) || 0) + 1);
  });
  const laneMax = new Map();
  const laneTop = new Map();
  let y = 0;
  for (const l of laneOrder) {
    laneTop.set(l.id, y);
    const laneActs = activities.filter((a) => a.lane === l.id);
    const maxGroup = Math.max(
      0,
      ...laneActs.map((a) => groupSizes.get(`${a.lane}:${levels.get(a.id)}`) || 0),
    );
    laneMax.set(l.id, maxGroup);
    y += Math.max(maxGroup, 1) * NODE_STEP;
  }

  // y final por atividade: grupo centralizado na faixa pelo CENTRO do card —
  // o React Flow posiciona pelo canto superior, então o topo do conjunto é
  // deslocado pela metade da altura do card ((size-1)*STEP + CARD)/2 de sobra
  const groupIdx = new Map();
  const yOf = new Map();
  [...activities]
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .forEach((a) => {
      const k = `${a.lane}:${levels.get(a.id)}`;
      const size = groupSizes.get(k) || 0;
      const maxGroup = Math.max(laneMax.get(a.lane), 1);
      const i = groupIdx.get(k) || 0;
      groupIdx.set(k, i + 1);
      yOf.set(
        a.id,
        laneTop.get(a.lane) + ((maxGroup - size + 1) * NODE_STEP - CARD_HEIGHT) / 2 + i * NODE_STEP,
      );
    });

  const graphWidth = (maxLevel + 1) * LEVEL_WIDTH;
  // dimensões totais do grafo (usadas para o fit-height na abertura do board)
  const graphHeight = y; // soma das alturas de todas as faixas

  const laneColor = new Map(laneOrder.map((l) => [l.id, l.color || "#000099"]));

  const nodes = [
    // banda de cada faixa: largura total do grafo, fundo zebrado (visível em
    // qualquer zoom) e divisor fino na borda inferior
    ...laneOrder.map((l, idx) => ({
      id: `band-${l.id}`,
      type: "laneBand",
      position: { x: 0, y: laneTop.get(l.id) },
      data: {
        width: graphWidth,
        height: Math.max(laneMax.get(l.id), 1) * NODE_STEP,
        alt: idx % 2 === 1,
      },
    })),
    ...activities.map((a) => ({
      id: String(a.id),
      type: "activity",
      position: { x: levels.get(a.id) * LEVEL_WIDTH, y: yOf.get(a.id) },
      data: { activity: a, level: levels.get(a.id), laneColor: laneColor.get(a.lane) },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    })),
    ...laneOrder.map((l) => {
      const laneActs = activities.filter((a) => a.lane === l.id);
      return {
        id: `lane-${l.id}`,
        type: "laneLabel",
        position: {
          x: LANE_LABEL_X,
          y: laneTop.get(l.id) + (Math.max(laneMax.get(l.id), 1) * NODE_STEP - LANE_LABEL_HEIGHT) / 2,
        },
        data: {
          label: l.label,
          color: l.color,
          width: LANE_LABEL_WIDTH,
          done: laneActs.filter((a) => a.status === "done").length,
          total: laneActs.length,
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

  return { nodes, edges, graphWidth, graphHeight, graphX: LANE_LABEL_X };
}
