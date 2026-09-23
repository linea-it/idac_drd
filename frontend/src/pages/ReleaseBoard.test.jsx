// Fluxo central: board em draft → Start execution → confirma → POST /start/.
// E garante que "Back to draft" não existe mais (decisão de produto).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import ReleaseBoard from "./ReleaseBoard";

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }));
vi.mock("../api", () => ({ api: apiMock, appUrl: (path) => path }));

const release = {
  id: 1,
  name: "Release Smoke",
  slug: "release-smoke",
  status: "draft",
  started_at: null,
  template_key: null,
  steps: [],
  progress: { total: 0, done: 0, pct: 0 },
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/") return Promise.resolve(release);
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  apiMock.post.mockResolvedValue({});
});

test("start execution confirma, mostra Starting e não repete o POST", async () => {
  let resolvePost;
  apiMock.post.mockImplementation((path) => {
    if (String(path).endsWith("/start/")) {
      return new Promise((resolve) => {
        resolvePost = () =>
          resolve({ ...release, status: "active", started_at: "2026-08-16T10:00:00Z" });
      });
    }
    return Promise.resolve({});
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  expect(await screen.findByText("Release Smoke")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Start execution" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Start execution" }));

  const starting = within(dialog).getByRole("button", { name: "Starting…" });
  expect(starting).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
  fireEvent.click(starting);
  expect(apiMock.post).toHaveBeenCalledTimes(1);
  expect(apiMock.post).toHaveBeenCalledWith("/api/releases/release-smoke/start/");

  resolvePost();
  expect(await screen.findByText("In execution")).toBeInTheDocument();
  expect(
    screen.getByText("Creating GitHub issues and GLPI tickets in the background."),
  ).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("não existe mais 'Back to draft' no board em draft", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");
  expect(screen.queryByText("Back to draft")).not.toBeInTheDocument();
  // as ações de draft continuam: Add step, Add activity, Start execution, Delete draft
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete draft" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
});

test("não-staff não vê ações de ciclo de vida (start/archive), só estrutura", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete draft" })).toBeInTheDocument();
  // edição estrutural e aprovação continuam para todos
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add activity" })).toBeInTheDocument();
});

test("em execução a edição é um toggle (Edit liga e desliga)", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, status: "active", started_at: "2026-08-16T10:00:00Z" });
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  // fora do modo de edição: só Edit, sem controles de edição
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add activity" })).not.toBeInTheDocument();
  // Edit habilita a edição
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add activity" })).toBeInTheDocument();
  // clicar de novo em Edit desliga o modo, sem Save/Cancel
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  // ações de draft exclusivas nunca aparecem em execução
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save as template" })).not.toBeInTheDocument();
});

test("em completed a edição também é um toggle", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, status: "completed" });
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  // fora do modo de edição: só Edit, sem controles de edição
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add activity" })).not.toBeInTheDocument();
  // Edit habilita a edição
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add activity" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  // ações de draft exclusivas nunca aparecem em completed
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
});

test("Export draft (JSON) busca o payload e dispara o download", async () => {
  // jsdom não provê createObjectURL/revokeObjectURL — stub para capturar o Blob
  const createObjectURL = vi.fn(() => "blob:mock");
  const revokeObjectURL = vi.fn();
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;

  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/") return Promise.resolve(release);
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    if (path === "/api/releases/release-smoke/export/")
      return Promise.resolve({
        format: "idac_drd-draft",
        version: 1,
        name: "Release Smoke",
        steps: [],
        activities: [],
      });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });

  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");

  fireEvent.click(screen.getByRole("button", { name: "Export draft (JSON)" }));

  await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith("/api/releases/release-smoke/export/"));
  expect(createObjectURL).toHaveBeenCalled();
  // o blob baixado é o próprio payload do export, como JSON
  const [blob] = createObjectURL.mock.calls[0];
  expect(blob.type).toContain("application/json");
  expect(JSON.parse(await blob.text()).format).toBe("idac_drd-draft");
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
});

test("em execução, Export só em edição e Download só fora; desligar Edit não recarrega", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, status: "active", started_at: "2026-08-16T10:00:00Z" });
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");

  // fora do modo de edição: Export escondido, Download visível
  expect(screen.queryByRole("button", { name: "Export draft (JSON)" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download report" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getByRole("button", { name: "Export draft (JSON)" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Download report" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();

  const getsBefore = apiMock.get.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.queryByRole("button", { name: "Export draft (JSON)" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download report" })).toBeInTheDocument();
  expect(apiMock.get.mock.calls.length).toBe(getsBefore);
});

test("setas do Kanban reordenam atividades dentro do step", async () => {
  const steps = [{ id: 1, key: "step-a", label: "Step A", order: 0, color: "#0989cb", resources: [] }];
  const mk = (id, key, label, order) => ({
    id,
    key,
    label,
    step: 1,
    order,
    status: "todo",
    mode: "manual",
    resources: [],
    depends_on: [],
    locked: false,
    prerequisites_met: true,
    objectives: "",
  });
  const first = mk(10, "a1", "First", 0);
  const second = mk(11, "a2", "Second", 1);
  // após o move, o reload devolve a ordem trocada
  let swapped = false;
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, status: "active", started_at: "2026-08-16T10:00:00Z", steps });
    if (path === "/api/releases/release-smoke/activities/")
      // o backend reordena via campo order: Second vira 0, First vira 2
      return Promise.resolve(swapped ? [{ ...second, order: 0 }, { ...first, order: 2 }] : [first, second]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  apiMock.post.mockImplementation(async (path, body) => {
    if (path === "/api/activities/10/move/" && body.after_id === 11) swapped = true;
    return {};
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  await screen.findByText("First");

  const cardOf = (label) => screen.getByText(label).closest(".MuiCard-root");
  // primeiro card: ↑ desabilitada, ↓ habilitada; último: o inverso
  expect(within(cardOf("First")).getByTitle("Move activity up")).toBeDisabled();
  expect(within(cardOf("First")).getByTitle("Move activity down")).toBeEnabled();
  expect(within(cardOf("Second")).getByTitle("Move activity up")).toBeEnabled();
  expect(within(cardOf("Second")).getByTitle("Move activity down")).toBeDisabled();

  fireEvent.click(within(cardOf("First")).getByTitle("Move activity down"));

  // chamou o move com after_id do card seguinte
  await waitFor(() =>
    expect(apiMock.post).toHaveBeenCalledWith("/api/activities/10/move/", { step_id: 1, after_id: 11 }),
  );
  // após o reload a ordem trocou: First agora é o último card
  await waitFor(() => expect(within(cardOf("First")).getByTitle("Move activity down")).toBeDisabled());
});

test("Make a copy no Kanban chama duplicate e abre a cópia", async () => {
  const steps = [{ id: 1, key: "step-a", label: "Step A", order: 0, color: "#0989cb", resources: [] }];
  const mk = (id, key, label, order, dependsOn = []) => ({
    id,
    key,
    label,
    step: 1,
    order,
    status: "todo",
    mode: "manual",
    resources: [],
    depends_on: dependsOn,
    locked: false,
    prerequisites_met: true,
    objectives: "",
    step_label: "Step A",
  });
  const first = mk(10, "a1", "First", 0);
  const second = mk(11, "a2", "Second", 1, [10]);
  const copy = mk(12, "copy-of-first", "Copy of First", 1);
  let duplicated = false;
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, status: "draft", steps });
    if (path === "/api/releases/release-smoke/activities/")
      return Promise.resolve(duplicated ? [first, copy, { ...second, order: 2 }] : [first, second]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    if (path === "/api/releases/release-smoke/transitions/") return Promise.resolve([]);
    if (path === "/api/releases/release-smoke/text-revisions/") return Promise.resolve([]);
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  apiMock.post.mockImplementation(async (path) => {
    if (path === "/api/activities/10/duplicate/") {
      duplicated = true;
      return copy;
    }
    return {};
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("First");

  fireEvent.click(within(screen.getByText("First").closest(".MuiCard-root")).getByTitle("Make a copy"));

  await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith("/api/activities/10/duplicate/", {}));
  expect(await screen.findByRole("heading", { name: "Copy of First" })).toBeInTheDocument();
});

test("options do GitHub com erro mostram banner sem derrubar o board", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/") return Promise.resolve(release);
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/")
      return Promise.resolve({ repos: [], areas: [], sizes: [], error: "GH_TOKEN not set" });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");
  expect(screen.getByText(/Couldn't load GitHub/)).toBeInTheDocument();
  expect(screen.getByText(/GH_TOKEN not set/)).toBeInTheDocument();
});

test("falha de rede nos options mostra banner com a mensagem", async () => {
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/") return Promise.resolve(release);
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.reject(new Error("Network Error"));
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");
  expect(screen.getByText(/Network Error/)).toBeInTheDocument();
});

// --- filtros facetados (#25) ---

test("barra de filtros presente: 4 facets + Showing N of M", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  expect(screen.getByLabelText("Assignee")).toBeInTheDocument();
  expect(screen.getByLabelText("Status")).toBeInTheDocument();
  expect(screen.getByLabelText("Mode")).toBeInTheDocument();
  expect(screen.getByLabelText("Area")).toBeInTheDocument();
  expect(screen.getByText("Showing 0 of 0")).toBeInTheDocument();
});

test("filtro de status destaca cards no Kanban sem alterar contadores", async () => {
  const steps = [{ id: 1, key: "step-a", label: "Step A", order: 0, color: "#0989cb", resources: [] }];
  const mk = (id, key, label, status) => ({
    id,
    key,
    label,
    step: 1,
    order: id,
    status,
    mode: "manual",
    resources: [],
    depends_on: [],
    locked: false,
    prerequisites_met: true,
    objectives: "",
  });
  const first = mk(10, "a1", "First", "todo");
  const second = mk(11, "a2", "Second", "done");
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, steps });
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([first, second]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("First");
  expect(screen.getByText("Showing 2 of 2")).toBeInTheDocument();

  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Status" }));
  fireEvent.click(await screen.findByRole("option", { name: "To do" }));

  expect(screen.getByText("Showing 1 of 2")).toBeInTheDocument();
  const cardOf = (label) => screen.getByText(label).closest(".MuiCard-root");
  // match permanece opaco; não-match cai para 0.35 (mesma opacidade do DAG)
  expect(cardOf("First")).toHaveStyle({ opacity: "1" });
  expect(cardOf("Second")).toHaveStyle({ opacity: "0.35" });
  // header do step usa a lista completa — contador não muda com o filtro
  const stepHeader = screen.getByText("Step A").closest(".MuiBox-root");
  expect(within(stepHeader).getByText("1/2 done")).toBeInTheDocument();
  // Clear aparece com o filtro ativo e zera tudo
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("Showing 2 of 2")).toBeInTheDocument();
  expect(cardOf("Second")).toHaveStyle({ opacity: "1" });
});

test("Hide unmatched remove cards e esconde colunas vazias no Kanban", async () => {
  const steps = [
    { id: 1, key: "step-a", label: "Step A", order: 0, color: "#0989cb", resources: [] },
    { id: 2, key: "step-b", label: "Step B", order: 1, color: "#31297f", resources: [] },
  ];
  const mk = (id, key, label, status, step) => ({
    id,
    key,
    label,
    step,
    order: id,
    status,
    mode: "manual",
    resources: [],
    depends_on: [],
    locked: false,
    prerequisites_met: true,
    objectives: "",
  });
  const first = mk(10, "a1", "First", "todo", 1);
  const second = mk(11, "a2", "Second", "done", 2);
  apiMock.get.mockImplementation((path) => {
    if (path === "/api/releases/release-smoke/")
      return Promise.resolve({ ...release, steps });
    if (path === "/api/releases/release-smoke/activities/") return Promise.resolve([first, second]);
    if (path === "/api/external-identities/") return Promise.resolve([]);
    if (path === "/api/github/options/") return Promise.resolve({ repos: [], areas: [], sizes: [] });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("First");
  expect(screen.getByText("Step B")).toBeInTheDocument();

  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Status" }));
  fireEvent.click(await screen.findByRole("option", { name: "To do" }));

  fireEvent.click(screen.getByRole("checkbox", { name: "Hide Unmatched" }));
  expect(screen.getByText("First")).toBeInTheDocument();
  expect(screen.queryByText("Second")).not.toBeInTheDocument();
  // coluna com match permanece (contador da lista completa); coluna vazia some
  expect(screen.getByText("Step A")).toBeInTheDocument();
  const stepHeader = screen.getByText("Step A").closest(".MuiBox-root");
  expect(within(stepHeader).getByText("0/1 done")).toBeInTheDocument();
  expect(screen.queryByText("Step B")).not.toBeInTheDocument();
  // Clear zera hide — switch volta a desabilitado e cards/colunas reaparecem
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("Second")).toBeInTheDocument();
  expect(screen.getByText("Step B")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Hide Unmatched" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "Hide Unmatched" })).not.toBeChecked();
});
