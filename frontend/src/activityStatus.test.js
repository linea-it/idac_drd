import { describe, expect, it } from "vitest";
import { displayStatus, isPrereqAutoBlock, isStuck, statusLabel } from "./activityStatus";

describe("displayStatus", () => {
  it("todo sem prereq → waiting", () => {
    expect(displayStatus({ status: "todo", prerequisites_met: false })).toBe("waiting");
  });

  it("auto-block do backend → waiting", () => {
    expect(
      displayStatus({
        status: "blocked",
        prerequisites_met: false,
        blocked_reason: "Waiting on prerequisites: Step 1",
      }),
    ).toBe("waiting");
  });

  it("legado PT auto-block → waiting", () => {
    expect(
      displayStatus({
        status: "blocked",
        prerequisites_met: false,
        blocked_reason: "Aguardando pré-requisitos: Passo 1",
      }),
    ).toBe("waiting");
  });

  it("blocked manual → blocked", () => {
    expect(
      displayStatus({
        status: "blocked",
        prerequisites_met: true,
        blocked_reason: "vendor delay",
      }),
    ).toBe("blocked");
    expect(isPrereqAutoBlock({ status: "blocked", blocked_reason: "vendor delay" })).toBe(false);
  });

  it("rótulo Waiting", () => {
    expect(statusLabel("waiting")).toBe("Waiting");
    expect(statusLabel("blocked")).toBe("Blocked");
  });
});

describe("isStuck", () => {
  it("true para waiting e blocked; false para todo pronto / in_progress", () => {
    expect(isStuck({ status: "todo", prerequisites_met: false })).toBe(true);
    expect(
      isStuck({
        status: "blocked",
        prerequisites_met: false,
        blocked_reason: "Waiting on prerequisites: X",
      }),
    ).toBe(true);
    expect(isStuck({ status: "blocked", prerequisites_met: true, blocked_reason: "vendor" })).toBe(true);
    expect(isStuck({ status: "todo", prerequisites_met: true })).toBe(false);
    expect(isStuck({ status: "in_progress", prerequisites_met: true })).toBe(false);
  });
});
