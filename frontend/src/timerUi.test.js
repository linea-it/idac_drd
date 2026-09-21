import { describe, expect, it } from "vitest";
import {
  canControlTimer,
  formatEffort,
  timerGateMessage,
  timerGateReason,
  workflowChip,
} from "./timerUi";

describe("formatEffort", () => {
  it("formata segundos", () => {
    expect(formatEffort(45)).toBe("45s");
    expect(formatEffort(90)).toBe("1m");
    expect(formatEffort(3661)).toBe("1h 1m");
  });
});

describe("canControlTimer / gate", () => {
  const act = { assignee: { email: "alice@linea.org.br" } };

  it("assignee por email", () => {
    expect(canControlTimer(act, { userEmail: "alice@linea.org.br" })).toBe(true);
    expect(canControlTimer(act, { userEmail: "bob@linea.org.br" })).toBe(false);
  });

  it("superuser", () => {
    expect(canControlTimer(act, { isSuperuser: true, userEmail: "" })).toBe(true);
  });

  it("mensagens de gate", () => {
    expect(timerGateMessage(timerGateReason(act, { userEmail: "bob@x.com" }))).toMatch(/assignee/);
    expect(timerGateMessage(timerGateReason(act, { userEmail: "" }))).toMatch(/no email/);
  });
});

describe("workflowChip", () => {
  const display = (a) => a.status;
  const label = (s) => s;
  const colors = { in_progress: "info", todo: "default" };

  it("In Progress / Paused no lugar de chip genérico", () => {
    expect(
      workflowChip({ status: "in_progress", is_playing: true }, display, label, colors),
    ).toEqual({ label: "In Progress", color: "info" });
    expect(
      workflowChip({ status: "in_progress", is_playing: false }, display, label, colors),
    ).toEqual({ label: "Paused", color: "default" });
  });
});
