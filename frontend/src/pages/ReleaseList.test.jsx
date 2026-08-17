// Diálogo "New release": a terceira origem (JSON file) lê um arquivo de plan
// e cria o plano via POST /api/releases/import/.
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

function planFile(content, name = "plan.json") {
  return new File([content], name, { type: "application/json" });
}

const VALID_PLAN = {
  format: "idac_drd-plan",
  version: 1,
  name: "DR Import",
  steps: [{ key: "a", label: "Step A", order: 0, color: "#000099", resources: [] }],
  activities: [{ key: "a1", label: "Act 1", step_key: "a", order: 0, depends_on: [] }],
};

async function openDialogWithJsonOrigin() {
  render(<ReleaseList />);
  fireEvent.click(await screen.findByRole("button", { name: "Create release" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("radio", { name: "JSON file" }));
  return dialog;
}

test("diálogo New release oferece a origem JSON file com seletor de arquivo", async () => {
  const dialog = await openDialogWithJsonOrigin();
  expect(dialog.querySelector('input[type="file"]')).toBeInTheDocument();
});

test("arquivo JSON válido pré-preenche o nome e importa no submit", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [planFile(JSON.stringify(VALID_PLAN), "dr1.json")] },
  });
  // o nome do arquivo vira sugestão (exact:false — o label do MUI tem o "*" do required)
  await waitFor(() => expect(screen.getByLabelText("Name", { exact: false })).toHaveValue("DR Import"));

  fireEvent.submit(dialog.querySelector("#create-release-form"));
  await waitFor(() =>
    expect(apiMock.post).toHaveBeenCalledWith("/api/releases/import/", {
      name: "DR Import",
      steps: VALID_PLAN.steps,
      activities: VALID_PLAN.activities,
    }),
  );
});

test("arquivo inválido mostra erro e não habilita o Create", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [planFile("isto não é json", "broken.json")] },
  });
  expect(await screen.findByText("Invalid JSON file.")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Name", { exact: false }), { target: { value: "X" } });
  // sem plano carregado, Create fica desabilitado mesmo com nome
  expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  expect(apiMock.post).not.toHaveBeenCalled();
});

test("arquivo sem steps/activities é rejeitado como inválido", async () => {
  const dialog = await openDialogWithJsonOrigin();
  fireEvent.change(dialog.querySelector('input[type="file"]'), {
    target: { files: [planFile(JSON.stringify({ name: "vazio" }), "empty.json")] },
  });
  expect(await screen.findByText("Invalid plan file: steps and activities are required.")).toBeInTheDocument();
});
