// Diálogo "New draft": a terceira origem (JSON file) lê um arquivo de draft
// e cria o draft via POST /api/releases/import/.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import ReleaseList from "./ReleaseList";

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }));
vi.mock("../api", () => ({ api: apiMock }));

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/") return Promise.resolve([]);
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  apiMock.post.mockResolvedValue({});
});

function draftFile(content, name = "draft.json") {
  return new File([content], name, { type: "application/json" });
}

const VALID_DRAFT = {
  format: "idac_drd-draft",
  version: 1,
  name: "DR Import",
  steps: [{ key: "a", label: "Step A", order: 0, color: "#000099", resources: [] }],
  activities: [{ key: "a1", label: "Act 1", step_key: "a", order: 0, depends_on: [] }],
};

async function openDialogWithJsonOrigin() {
  render(<ReleaseList page="drafts" />);
  fireEvent.click(await screen.findByRole("button", { name: "New draft" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("radio", { name: "JSON file" }));
  return dialog;
}

test("diálogo New draft oferece a origem JSON file com seletor de arquivo", async () => {
  const dialog = await openDialogWithJsonOrigin();
  expect(dialog.querySelector('input[type="file"]')).toBeInTheDocument();
});

test("arquivo JSON válido pré-preenche o nome e importa no submit", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [draftFile(JSON.stringify(VALID_DRAFT), "dr1.json")] },
  });
  // o nome do arquivo vira sugestão (exact:false — o label do MUI tem o "*" do required)
  await waitFor(() => expect(screen.getByLabelText("Name", { exact: false })).toHaveValue("DR Import"));

  fireEvent.submit(dialog.querySelector("#create-release-form"));
  await waitFor(() =>
    expect(apiMock.post).toHaveBeenCalledWith("/api/releases/import/", {
      name: "DR Import",
      steps: VALID_DRAFT.steps,
      activities: VALID_DRAFT.activities,
    }),
  );
});

test("arquivo inválido mostra erro e não habilita o Create", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [draftFile("isto não é json", "broken.json")] },
  });
  expect(await screen.findByText("This file isn't valid JSON.")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Name", { exact: false }), { target: { value: "X" } });
  // sem draft carregado, Create fica desabilitado mesmo com nome
  expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  expect(apiMock.post).not.toHaveBeenCalled();
});

test("arquivo sem steps/activities é rejeitado como inválido", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [draftFile(JSON.stringify({ name: "vazio" }), "empty.json")] },
  });
  expect(await screen.findByText("This file needs a steps list and an activities list.")).toBeInTheDocument();
});

test("New draft só aparece na página Drafts", async () => {
  render(<ReleaseList page="releases" />);
  await screen.findByRole("heading", { name: "Releases" });
  expect(screen.queryByRole("button", { name: "New draft" })).not.toBeInTheDocument();
});

test("página Releases agrupa em execução e concluídas", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/")
      return Promise.resolve([
        { id: 1, name: "DR1", slug: "dr1", status: "active", steps: [], progress: { done: 0, total: 1, pct: 0 } },
        { id: 2, name: "DR0", slug: "dr0", status: "completed", steps: [], progress: { done: 1, total: 1, pct: 100 } },
      ]);
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseList page="releases" />);
  expect(await screen.findByText("In execution (1)")).toBeInTheDocument();
  expect(screen.getByText("Completed (1)")).toBeInTheDocument();
  expect(screen.getByText("DR1")).toBeInTheDocument();
  expect(screen.getByText("DR0")).toBeInTheDocument();
});
