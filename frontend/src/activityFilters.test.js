import { describe, expect, it } from "vitest";
import { buildFilterOptions, isFilterActive, matchesFilters, UNASSIGNED } from "./activityFilters";

const act = (over = {}) => ({
  id: 1,
  status: "todo",
  prerequisites_met: true,
  assignee: { id: 7, name: "Ana" },
  mode: "manual",
  area: "Payments",
  ...over,
});

const empty = { assignees: [], statuses: [], modes: [], areas: [] };

describe("matchesFilters", () => {
  it("facets vazios → tudo match", () => {
    expect(matchesFilters(act(), empty)).toBe(true);
    expect(matchesFilters(act({ mode: "nifi", area: "", assignee: null }), empty)).toBe(true);
    expect(matchesFilters(act({ status: "done" }), empty)).toBe(true);
  });

  it("assignee OR dentro do facet + unassigned", () => {
    const f = { ...empty, assignees: [7, 9, UNASSIGNED] };
    expect(matchesFilters(act(), f)).toBe(true); // 7 está na lista
    expect(matchesFilters(act({ assignee: { id: 9 } }), f)).toBe(true); // 9 está na lista
    expect(matchesFilters(act({ assignee: null }), f)).toBe(true); // sem assignee → UNASSIGNED
    expect(matchesFilters(act({ assignee: { id: 3 } }), f)).toBe(false);
  });

  it("status waiting via prerequisites_met: false + status todo (displayStatus)", () => {
    const f = { ...empty, statuses: ["waiting"] };
    expect(matchesFilters(act({ status: "todo", prerequisites_met: false }), f)).toBe(true);
    // todo com pré-requisito ok NÃO é waiting
    expect(matchesFilters(act(), f)).toBe(false);
    // blocked manual NÃO entra no facet waiting
    expect(matchesFilters(act({ status: "blocked", blocked_reason: "vendor delay" }), f)).toBe(false);
  });

  it("auto-block do backend (Waiting on prerequisites) aparece como waiting", () => {
    const f = { ...empty, statuses: ["waiting"] };
    const auto = act({
      status: "blocked",
      prerequisites_met: false,
      blocked_reason: "Waiting on prerequisites: Step 1",
    });
    expect(matchesFilters(auto, f)).toBe(true);
    expect(matchesFilters(auto, { ...empty, statuses: ["blocked"] })).toBe(false);
  });

  it("blocked manual permanece distinto de waiting", () => {
    const f = { ...empty, statuses: ["blocked"] };
    expect(matchesFilters(act({ status: "blocked", blocked_reason: "vendor delay" }), f)).toBe(true);
    expect(matchesFilters(act({ status: "todo", prerequisites_met: false }), f)).toBe(false);
  });

  it("AND entre facets", () => {
    const f = { assignees: [7], statuses: ["todo"], modes: ["manual"], areas: ["Payments"] };
    expect(matchesFilters(act(), f)).toBe(true);
    expect(matchesFilters(act({ mode: "nifi" }), f)).toBe(false); // mode não bate
    expect(matchesFilters(act({ status: "done" }), f)).toBe(false); // status não bate
    expect(matchesFilters(act({ assignee: { id: 2 } }), f)).toBe(false); // assignee não bate
  });

  it("área e mode comparados por valor exato", () => {
    const f = { ...empty, modes: ["nifi"], areas: ["Payments"] };
    expect(matchesFilters(act({ mode: "nifi" }), f)).toBe(true);
    expect(matchesFilters(act({ mode: "manual" }), f)).toBe(false);
    expect(matchesFilters(act({ area: "payments" }), f)).toBe(false); // case-sensitive
    expect(matchesFilters(act({ area: "Payments " }), f)).toBe(false); // sem trim mágico
  });

  it("área vazia só entra se o facet incluir \"\"", () => {
    const f = { ...empty, areas: [""] };
    expect(matchesFilters(act({ area: "" }), f)).toBe(true);
    expect(matchesFilters(act({ area: null }), f)).toBe(true); // area null/undefined → ""
    expect(matchesFilters(act(), f)).toBe(false);
  });

  it("filters undefined/null → tudo match (defensivo)", () => {
    expect(matchesFilters(act(), undefined)).toBe(true);
    expect(matchesFilters(act(), null)).toBe(true);
  });
});

describe("buildFilterOptions", () => {
  it("lista assignees com id + Unassigned quando há atividade sem assignee", () => {
    const opts = buildFilterOptions([act(), act({ id: 2, assignee: null })]);
    expect(opts.assignees.map((o) => o.id)).toEqual([7, UNASSIGNED]); // sorted by label
    expect(opts.assignees.find((o) => o.id === UNASSIGNED).label).toBe("Unassigned");
  });

  it("statuses vêm do displayStatus (waiting aparece sem status cru waiting)", () => {
    const opts = buildFilterOptions([
      act(),
      act({ id: 2, status: "todo", prerequisites_met: false }),
      act({
        id: 3,
        status: "blocked",
        prerequisites_met: false,
        blocked_reason: "Waiting on prerequisites: Step 1",
      }),
      act({ id: 4, status: "done" }),
    ]);
    expect(opts.statuses).toContain("waiting");
    expect(opts.statuses).toContain("todo");
    expect(opts.statuses).toContain("done");
    expect(opts.statuses).not.toContain("blocked");
  });

  it("áreas vazias ficam fora; só valores presentes não-vazios", () => {
    const opts = buildFilterOptions([act(), act({ id: 2, area: "" }), act({ id: 3, area: null })]);
    expect(opts.areas).toEqual(["Payments"]);
  });

  it("modes agrupa manual/nifi sem duplicar", () => {
    const opts = buildFilterOptions([act(), act({ id: 2, mode: "nifi" }), act({ id: 3, mode: "nifi" })]);
    expect(opts.modes).toEqual(["manual", "nifi"]);
  });
});

describe("isFilterActive", () => {
  it("false com todos os facets vazios", () => {
    expect(isFilterActive(empty)).toBe(false);
    expect(isFilterActive(undefined)).toBe(false);
  });

  it("true quando qualquer facet tem valor", () => {
    expect(isFilterActive({ ...empty, statuses: ["todo"] })).toBe(true);
    expect(isFilterActive({ ...empty, assignees: [UNASSIGNED] })).toBe(true);
    expect(isFilterActive({ ...empty, modes: ["nifi"] })).toBe(true);
    expect(isFilterActive({ ...empty, areas: ["Payments"] })).toBe(true);
  });
});
