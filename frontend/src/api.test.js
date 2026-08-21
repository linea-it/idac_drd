import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { appUrl } from "./api";

describe("appUrl", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("sem prefixo devolve o path", () => {
    expect(appUrl("/releases/test/")).toBe("/releases/test/");
  });

  it("com data-api-prefix prefixa paths absolutos", () => {
    document.body.innerHTML = `<div id="idac-drd-root" data-api-prefix="/drd"></div>`;
    expect(appUrl("/releases/test/")).toBe("/drd/releases/test/");
    expect(appUrl("/")).toBe("/drd/");
  });

  it("não duplica o prefixo", () => {
    document.body.innerHTML = `<div id="idac-drd-root" data-api-prefix="/drd"></div>`;
    expect(appUrl("/drd/releases/test/")).toBe("/drd/releases/test/");
  });
});
