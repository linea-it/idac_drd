// Filtros facetados do ReleaseBoard (#25). Derivação client-side sobre
// `activities`: dentro de um facet os valores fazem OR; entre facets, AND.
// Facet vazio = pass-all (não restringe). Fonte de verdade: `activities`
// carregadas em ReleaseBoard — nada disso chega à API.
import { displayStatus } from "./activityStatus";

// Chave que representa "sem assignee" no facet de assignees.
export const UNASSIGNED = "__unassigned__";

// filters: { assignees: (number|UNASSIGNED)[], statuses: string[], modes: string[], areas: string[] }
// Regras:
// - Status compara filterStatus(activity): displayStatus, com in_progress
//   sem sessão (tag Paused) separado de In Progress (timer ligado).
// - "blocked" no facet é só o status manual do banco.
// - Assignee compara activity.assignee?.id, com UNASSIGNED para sem assignee.
// - Mode: activity.mode ("manual" | "nifi").
// - Area: string exata; área vazia só entra se o facet incluir "" (a barra
//   não oferece essa opção no v1).
// Mesma distinção do chip: in_progress com timer ligado fica "in_progress";
// in_progress sem sessão é a tag Paused.
export function filterStatus(activity) {
  const status = displayStatus(activity);
  if (status === "in_progress" && !activity.is_playing) return "paused";
  return status;
}

export function matchesFilters(activity, filters) {
  if (!filters) return true;
  const status = filterStatus(activity);
  const assigneeKey = activity.assignee?.id ?? UNASSIGNED;
  const mode = activity.mode ?? "manual";
  const area = activity.area ?? "";
  const inFacet = (values, value) => !values?.length || values.includes(value);
  return (
    inFacet(filters.assignees, assigneeKey) &&
    inFacet(filters.statuses, status) &&
    inFacet(filters.modes, mode) &&
    inFacet(filters.areas, area)
  );
}

// Ordem canônica dos valores — estabiliza a identidade/ordem das options dos
// Autocompletes entre renders.
const STATUS_ORDER = ["todo", "waiting", "blocked", "in_progress", "paused", "in_review", "done"];
const MODE_ORDER = ["manual", "nifi"];
const byOrder = (order) => (a, b) => order.indexOf(a) - order.indexOf(b);

// Opções de cada facet derivadas das atividades presentes.
// - assignees: [{ id: number|UNASSIGNED, label }] (inclui "Unassigned" quando há
//   atividade sem assignee).
// - statuses/modes/areas: listas de strings; áreas vazias ficam fora (v1 não
//   oferece "blank").
export function buildFilterOptions(activities) {
  const assignees = new Map();
  const statuses = new Set();
  const modes = new Set();
  const areas = new Set();
  for (const a of activities) {
    const key = a.assignee?.id ?? UNASSIGNED;
    if (!assignees.has(key)) {
      assignees.set(key, {
        id: key,
        label: a.assignee ? a.assignee.name || a.assignee.email : "Unassigned",
      });
    }
    statuses.add(filterStatus(a));
    modes.add(a.mode ?? "manual");
    if (a.area) areas.add(a.area);
  }
  return {
    assignees: [...assignees.values()].sort((x, y) => x.label.localeCompare(y.label)),
    statuses: [...statuses].sort(byOrder(STATUS_ORDER)),
    modes: [...modes].sort(byOrder(MODE_ORDER)),
    areas: [...areas].sort((x, y) => x.localeCompare(y)),
  };
}

// Há algum facet com valor selecionado? (qualquer facet com length > 0)
export function isFilterActive(filters) {
  return Boolean(
    filters &&
      (filters.assignees?.length ||
        filters.statuses?.length ||
        filters.modes?.length ||
        filters.areas?.length),
  );
}

export const EMPTY_FILTERS = { assignees: [], statuses: [], modes: [], areas: [] };
