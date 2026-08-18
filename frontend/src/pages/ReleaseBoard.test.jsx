// Fluxo central: board em draft → Start execution → confirma → POST /start/.
// E garante que "Back to draft" não existe mais (decisão de produto).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import ReleaseBoard from "./ReleaseBoard";

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }));
vi.mock("../api", () => ({ api: apiMock }));

const release = {
  id: 1,
  name: "Release Smoke",
  slug: "release-smoke",
  status: "planned",
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

test("start execution confirma e chama o endpoint", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  expect(await screen.findByText("Release Smoke")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Start execution" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Start execution" }));

  await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith("/api/releases/release-smoke/start/"));
});

test("não existe mais 'Back to draft' no board em draft", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");
  expect(screen.queryByText("Back to draft")).not.toBeInTheDocument();
  // as ações de draft continuam: Add step, Add activity, Start execution, Archive
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
});

test("não-staff não vê ações de ciclo de vida (start/archive), só estrutura", async () => {
  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={false} />);
  await screen.findByText("Release Smoke");
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  // edição estrutural e aprovação continuam para todos
  expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add activity" })).toBeInTheDocument();
});

test("em execução a edição é um modo explícito (Edit → Save)", async () => {
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
  // Save finaliza o modo
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  // ações de draft exclusivas nunca aparecem em execução
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save as template" })).not.toBeInTheDocument();
});

test("em completed a edição também é um modo explícito (Edit → Save)", async () => {
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
  // Save finaliza o modo
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
  // ações de draft exclusivas nunca aparecem em completed
  expect(screen.queryByRole("button", { name: "Start execution" })).not.toBeInTheDocument();
});

test("Export plan (JSON) busca o payload e dispara o download", async () => {
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
        format: "idac_drd-plan",
        version: 1,
        name: "Release Smoke",
        steps: [],
        activities: [],
      });
    return Promise.reject(new Error(`unexpected: ${path}`));
  });

  render(<ReleaseBoard releaseSlug="release-smoke" isStaff={true} />);
  await screen.findByText("Release Smoke");

  fireEvent.click(screen.getByRole("button", { name: "Export plan (JSON)" }));

  await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith("/api/releases/release-smoke/export/"));
  expect(createObjectURL).toHaveBeenCalled();
  // o blob baixado é o próprio payload do export, como JSON
  const [blob] = createObjectURL.mock.calls[0];
  expect(blob.type).toContain("application/json");
  expect(JSON.parse(await blob.text()).format).toBe("idac_drd-plan");
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
});

test("em execução, Export só em edição, Download só fora; Cancel sai recarregando", async () => {
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
  expect(screen.queryByRole("button", { name: "Export plan (JSON)" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download report" })).toBeInTheDocument();

  // Edit habilita: Export aparece, Download some, Cancel + Save disponíveis
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getByRole("button", { name: "Export plan (JSON)" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Download report" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();

  // Cancel desiste: recarrega do servidor e volta ao estado anterior ao Edit
  const getsBefore = apiMock.get.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("button", { name: "Export plan (JSON)" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download report" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  await waitFor(() => expect(apiMock.get.mock.calls.length).toBeGreaterThan(getsBefore));
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
