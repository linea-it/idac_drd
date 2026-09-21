import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useStore,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { computeDagState, DAG_VIEWPORT_VERSION } from "../dagState";
import { edgeStyleFor } from "../edgeStyles";
import ActivityFlowNode from "./ActivityFlowNode";
import StepBandNode from "./StepBandNode";
import StepLabelNode from "./StepLabelNode";

const nodeTypes = { activity: ActivityFlowNode, stepBand: StepBandNode, stepLabel: StepLabelNode };

// selectedId: abre ?activity= com o nó focado; flash: anel no card recém-editado.
// matchedIds/filterActive: dim do filtro facetado (#25) — nunca remove nós/arestas.
export default function ActivityDagBoard({
  steps,
  activities,
  onSelect,
  selectedId = null,
  flash = null,
  matchedIds = null,
  filterActive = false,
  onPlay,
  onPause,
  isSuperuser = false,
  userEmail = "",
}) {
  return (
    <ReactFlowProvider>
      <DagInner
        steps={steps}
        activities={activities}
        onSelect={onSelect}
        selectedId={selectedId}
        flash={flash}
        matchedIds={matchedIds}
        filterActive={filterActive}
        onPlay={onPlay}
        onPause={onPause}
        isSuperuser={isSuperuser}
        userEmail={userEmail}
      />
    </ReactFlowProvider>
  );
}

function DagInner({
  steps,
  activities,
  onSelect,
  selectedId,
  flash,
  matchedIds,
  filterActive,
  onPlay,
  onPause,
  isSuperuser,
  userEmail,
}) {
  const theme = useTheme();
  const { fitView, setViewport, getViewport } = useReactFlow();
  // dimensões do canvas vêm do store (useReactFlow não as expõe);
  // seletores primitivos separados — objeto novo por snapshot causaria loop de render
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  // viewport persiste por release; DAG_VIEWPORT_VERSION invalida caches após
  // mudanças de layout/fit (altura do canvas, rows, pathOptions, …)
  const viewportKey = useMemo(
    () =>
      `idac_drd:dagViewport:v${DAG_VIEWPORT_VERSION}:${[...steps]
        .map((l) => l.id)
        .sort((a, b) => a - b)
        .join(",")}`,
    [steps],
  );
  const { nodes, edges, graphWidth, graphHeight, graphX } = useMemo(
    () => computeDagState(activities, steps),
    [activities, steps],
  );
  const [revealed, setRevealed] = useState(false);
  const [hoverId, setHoverId] = useState(null);
  const [flashActive, setFlashActive] = useState(false);
  // o hover só liga depois de ~250ms com o mouse parado no mesmo nó:
  // durante zoom/pan o conteúdo desliza sob o cursor e o dim piscaria a cada frame
  const hoverTimer = useRef(null);

  // revelação progressiva: só na MONTAGEM (double rAF garante o paint inicial) —
  // edições posteriores não re-animam o grafo inteiro
  useEffect(() => {
    setRevealed(false);
    let raf1;
    let raf2;
    raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setRevealed(true));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, []);

  useEffect(() => () => clearTimeout(hoverTimer.current), []);

  // ao abrir: restaura o zoom/posição salvos desta release (se houver); senão,
  // fit por ALTURA — o grafo inteiro (todas as faixas) cabe verticalmente com
  // margem de 15%. Só na primeira vez — edições posteriores não resetam o viewport
  const didFitHeight = useRef(false);
  useEffect(() => {
    if (didFitHeight.current || !width || !height || !graphHeight) return;
    didFitHeight.current = true;
    const saved = sessionStorage.getItem(viewportKey);
    if (saved) {
      try {
        const vp = JSON.parse(saved);
        if (typeof vp.x === "number" && typeof vp.y === "number" && typeof vp.zoom === "number") {
          setViewport(vp);
          return;
        }
      } catch {
        // storage inválido: cai no fit-height
      }
    }
    const padding = 0.15;
    const zoom = (height * (1 - 2 * padding)) / graphHeight;
    // borda esquerda do grafo (rótulos das faixas) alinhada à margem; y centralizado
    setViewport({
      x: width * padding - graphX * zoom,
      y: (height - graphHeight * zoom) / 2,
      zoom,
    });
  }, [width, height, graphHeight, graphX, setViewport, viewportKey]);

  // salva o viewport ao sair do DAG (troca de aba desmonta o componente)
  useEffect(() => {
    return () => {
      if (!nodes.length) return;
      sessionStorage.setItem(viewportKey, JSON.stringify(getViewport()));
    };
  }, [viewportKey, nodes, getViewport]);

  // anel de destaque no card recém-editado (cor do status atual), ~2.4s
  useEffect(() => {
    if (!flash) return;
    setFlashActive(true);
    const t = setTimeout(() => setFlashActive(false), 2400);
    return () => clearTimeout(t);
  }, [flash]);

  // quando uma activity é aberta via ?activity= (link direto / F5), focar o nó
  useEffect(() => {
    if (!selectedId || !nodes.some((n) => n.id === String(selectedId))) return;
    const t = setTimeout(() => {
      fitView({ nodes: [{ id: String(selectedId) }], padding: 0.6, duration: 700, maxZoom: 1 });
    }, 350);
    return () => clearTimeout(t);
  }, [selectedId, nodes, fitView]);

  // vizinhos diretos do nó sob o mouse (pré-requisitos + dependentes)
  const neighbors = useMemo(() => {
    if (!hoverId) return new Set();
    const s = new Set();
    for (const e of edges) {
      if (e.source === hoverId) s.add(e.target);
      if (e.target === hoverId) s.add(e.source);
    }
    return s;
  }, [hoverId, edges]);

  const flowNodes = useMemo(
    () =>
      nodes.map((n) => {
        // filtro (#25): esmaece atividades que não batem; hover vence enquanto ativo
        const filterDim = filterActive && n.type === "activity" && !matchedIds?.has(Number(n.id));
        // hover: esmaece tudo que não é o nó nem seus vizinhos diretos
        const hoverDim = hoverId && n.type === "activity" && n.id !== hoverId && !neighbors.has(n.id);
        const dim = hoverId ? hoverDim : filterDim;
        return {
          ...n,
          data: {
            ...n.data,
            revealed,
            dim,
            flash: flashActive && flash?.id === n.id,
            onPlay,
            onPause,
            isSuperuser,
            userEmail,
          },
        };
      }),
    [
      nodes,
      revealed,
      hoverId,
      neighbors,
      flashActive,
      flash,
      filterActive,
      matchedIds,
      onPlay,
      onPause,
      isSuperuser,
      userEmail,
    ],
  );

  // hover: arestas conectadas mais grossas, o resto esmaece; senão, o filtro
  // esmaece arestas com source OU target fora do match; sem nada, estilo padrão
  const styledEdges = useMemo(() => {
    const connected = hoverId ? new Set() : null;
    if (connected) {
      for (const e of edges) {
        if (e.source === hoverId || e.target === hoverId) connected.add(e.id);
      }
    }
    return edges.map((e) => {
      const base = edgeStyleFor(e.targetStatus, theme);
      const isConn = connected?.has(e.id);
      const filterConn =
        !hoverId &&
        filterActive &&
        matchedIds?.has(Number(e.source)) &&
        matchedIds?.has(Number(e.target));
      let opacity = 1;
      if (hoverId) opacity = isConn ? 1 : 0.15;
      else if (filterActive) opacity = filterConn ? 1 : 0.15;
      return {
        ...e,
        type: "smoothstep",
        ...base,
        style: {
          ...base.style,
          strokeWidth: isConn ? 2.5 : base.style.strokeWidth,
          opacity,
          pointerEvents: "none",
        },
      };
    });
  }, [edges, theme, hoverId, filterActive, matchedIds]);

  const doneCount = activities.filter((a) => a.status === "done").length;

  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">
        {doneCount}/{activities.length} done · arrows point from a prerequisite to its dependents
      </Typography>
      <Box
        sx={{
          // mais área vertical → fit-height inicial com zoom maior (mais steps visíveis)
          height: "calc(100vh - 140px)",
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          overflow: "hidden",
        }}
      >
        <ReactFlow
          nodes={flowNodes}
          edges={styledEdges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          minZoom={0.1}
          deleteKeyCode={null}
          onNodeClick={(_, node) => node.type === "activity" && onSelect(node.data.activity)}
          onMoveEnd={(_, viewport) => sessionStorage.setItem(viewportKey, JSON.stringify(viewport))}
          nodesConnectable={false}
          edgesFocusable={false}
          onNodeMouseEnter={(_, node) => {
            if (node.type !== "activity") return;
            clearTimeout(hoverTimer.current);
            hoverTimer.current = setTimeout(() => setHoverId(node.id), 250);
          }}
          onNodeMouseLeave={() => {
            // debounce: o re-render do dim dispara leave no wrapper do RF;
            // se o enter voltar antes disto, o hover se mantém
            clearTimeout(hoverTimer.current);
            hoverTimer.current = setTimeout(() => setHoverId(null), 80);
          }}
        >
          <Background variant="dots" gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Box>
    </Stack>
  );
}
