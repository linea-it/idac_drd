// Estilo das arestas da DAG por status do nó ALVO (o dependente).
// Edite aqui: tokens de cor do tema MUI, espessura, tracejado e animação.
// `animated: true` = traço em movimento contínuo (dash animado do React Flow).
// Toda aresta recebe uma seta (markerEnd) na mesma cor da linha.
import { MarkerType } from "@xyflow/react";

export function edgeStyleFor(status, theme) {
  const styles = {
    done: {
      stroke: theme.palette.success.main,
      strokeWidth: 1.5,
      animated: false,
    },
    in_progress: {
      stroke: theme.palette.info.main,
      strokeWidth: 1.5,
      animated: true,
    },
    in_review: {
      stroke: theme.palette.secondary.main,
      strokeWidth: 1.5,
      animated: true,
    },
    todo: {
      stroke: theme.palette.divider,
      strokeWidth: 1.5,
      animated: false,
    },
    blocked: {
      stroke: theme.palette.warning.main,
      strokeWidth: 1.5,
      animated: false,
    },
  };
  const s = styles[status] || styles.todo;
  return {
    animated: s.animated,
    // o React Flow lê a aparência da linha da prop `style` do edge (não do nível raiz)
    style: {
      stroke: s.stroke,
      strokeWidth: s.strokeWidth,
      strokeDasharray: s.strokeDasharray,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: s.stroke, width: 18, height: 18 },
  };
}
