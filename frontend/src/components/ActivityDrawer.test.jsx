// O pivô: o draft é editável também em execução — o save sempre manda o
// payload estrutural completo. A única restrição de modo: status não muda em
// draft (a execução só começa após o gesto de start).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { api } from "../api";
import ActivityDrawer from "./ActivityDrawer";

vi.mock("../api", () => ({ api: { get: vi.fn(() => Promise.resolve([])) } }));

const activity = {
  id: 1,
  key: "step-1",
  label: "Step 1",
  step: 1,
  step_label: "Step A",
  status: "in_progress",
  mode: "manual",
  github_repo: "",
  area: "",
  size: "",
  description: "",
  objectives: "",
  notes: "",
  blocked_reason: "",
  assignee: null,
  depends_on: [],
  locked: false,
};

function renderDrawer(draft, canEdit = true) {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onClose = vi.fn();
  const view = render(
    <ActivityDrawer
      open
      activity={activity}
      releaseSlug="r1"
      users={[]}
      githubOptions={{ repos: ["linea-it/x"], areas: ["Ingestão"], sizes: ["M"] }}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[activity]}
      readonly={false}
      draft={draft}
      canEdit={canEdit}
      onClose={onClose}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );
  return { onSave, onClose, unmount: view.unmount };
}

test("em execução envia o payload estrutural completo", async () => {
  const { onSave, onClose } = renderDrawer(false);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
  expect(onClose).not.toHaveBeenCalled();
  expect(onSave).toHaveBeenCalledWith({
    status: "in_progress",
    assignee_id: null,
    notes: "",
    blocked_reason: "",
    mode: "manual",
    label: "Step 1",
    description: "",
    objectives: "",
    step_id: 1,
    depends_on_ids: [],
    github_repo: "",
    area: "",
    size: "",
    resources: [],
  });
});

test("no draft envia o payload estrutural completo também", async () => {
  const { onSave } = renderDrawer(true);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
  expect(onSave).toHaveBeenCalledWith(
    expect.objectContaining({
      status: "in_progress",
      assignee_id: null,
      mode: "manual",
      label: "Step 1",
      description: "",
      step_id: 1,
      depends_on_ids: [],
      github_repo: "",
      area: "",
      size: "",
      resources: [],
    }),
  );
});

test("em execução sem modo de edição a estrutura fica desabilitada", async () => {
  const first = renderDrawer(false, false);
  // TextField MUI: input com disabled prop de verdade
  expect(screen.getByLabelText("Label")).toHaveProperty("disabled", true);
  first.unmount();
  // e o payload do Save não inclui a estrutura fora do modo de edição
  const { onSave } = renderDrawer(false, false);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
  expect(onSave).not.toHaveBeenCalledWith(expect.objectContaining({ label: "Step 1" }));
});

test("status fica desabilitado em draft (transição só após o start)", async () => {
  const { unmount } = renderDrawer(true);
  const statusControl = screen.getByText("Status", { selector: "label" }).closest(".MuiFormControl-root");
  // MUI marca disabled via classe .Mui-disabled no root do InputBase
  expect(statusControl.querySelector(".MuiInputBase-root")).toHaveClass("Mui-disabled");
  unmount();
  // em execução o status volta a ficar ativo
  const view = render(
    <ActivityDrawer
      open
      activity={activity}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[activity]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={vi.fn()}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );
  const activeControl = screen.getByText("Status", { selector: "label" }).closest(".MuiFormControl-root");
  expect(activeControl.querySelector(".MuiInputBase-root")).not.toHaveClass("Mui-disabled");
  view.unmount();
});

test("em execução o checklist persiste e o Complete exige todos", async () => {
  const withObjectives = {
    ...activity,
    status: "in_progress",
    effort_seconds: 12,
    objectives: "Validar schema\nGerar dataset",
  };
  const onSave = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <ActivityDrawer
      open
      activity={withObjectives}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[withObjectives]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  const completeButton = screen.getByRole("button", { name: "Complete" });
  expect(screen.getByText("Validar schema")).toBeInTheDocument();
  expect(screen.getByText("Gerar dataset")).toBeInTheDocument();

  expect(completeButton).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText("Validar schema"));
  await waitFor(() =>
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        status: "in_progress",
        objectives: "[x] Validar schema\n[ ] Gerar dataset",
      }),
    ),
  );
  expect(completeButton).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText("Gerar dataset"));
  expect(completeButton).toHaveProperty("disabled", false);
  fireEvent.click(completeButton);
  await waitFor(() =>
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        status: "done",
        objectives: "[x] Validar schema\n[x] Gerar dataset",
      }),
    ),
  );
  view.unmount();
});

test("em execução o status vira ação: Complete em in_progress", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const withEffort = { ...activity, effort_seconds: 12 };
  const view = render(
    <ActivityDrawer
      open
      activity={withEffort}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[withEffort]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  const sendButton = screen.getByRole("button", { name: "Complete" });
  expect(sendButton).toHaveProperty("disabled", false);
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  fireEvent.click(sendButton);
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ status: "done" })));
  view.unmount();
});

test("Complete fica desabilitado sem effort nem play", () => {
  const withAssignee = {
    ...activity,
    effort_seconds: 0,
    is_playing: false,
    assignee: { id: 1, email: "alice@linea.org.br", name: "Alice" },
  };
  const view = render(
    <ActivityDrawer
      open
      activity={withAssignee}
      releaseSlug="r1"
      users={[withAssignee.assignee]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[withAssignee]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={() => {}}
      onDelete={() => {}}
      onMove={() => {}}
      onPlay={() => {}}
      onRecordEffort={() => {}}
      userEmail="alice@linea.org.br"
    />,
  );
  expect(screen.getByRole("button", { name: "Complete" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(
    screen.getByText("No effort yet — use Play or Add Effort first"),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Minutes")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add Effort" }));
  expect(screen.getByLabelText("Minutes")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save effort" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cancel effort" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add Effort" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel effort" }));
  expect(screen.queryByLabelText("Minutes")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add Effort" })).toBeInTheDocument();
  view.unmount();
});

test("colchetes de persistência não aparecem no dashboard e o save re-aplica a marcação", async () => {
  const withChecked = {
    ...activity,
    status: "in_progress",
    objectives: "[x] Criar schemas\n[ ] Processar ingestao",
  };
  const onSave = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <ActivityDrawer
      open
      activity={withChecked}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[withChecked]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  // o campo mostra o texto limpo, sem [x]/[ ]
  expect(screen.getByLabelText("Objectives")).toHaveValue("Criar schemas\nProcessar ingestao");

  // o save re-grava a marcação (formato de persistência para os tickets)
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ objectives: "[x] Criar schemas\n[ ] Processar ingestao" }),
    ),
  );
  view.unmount();
});

test("selecionar o status salva na hora e não fecha o drawer", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onClose = vi.fn();
  const view = render(
    <ActivityDrawer
      open
      activity={{ ...activity, status: "todo" }}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[activity]}
      readonly={false}
      draft={false}
      onClose={onClose}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  fireEvent.mouseDown(screen.getAllByRole("combobox")[0]);
  fireEvent.click(await screen.findByText("In progress"));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ status: "in_progress" })));
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Complete" })).not.toBeInTheDocument();
  view.unmount();
});

test("em blocked não há botão de conclusão", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <ActivityDrawer
      open
      activity={{ ...activity, status: "blocked", blocked_reason: "Waiting on prerequisites: Step 1" }}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[activity]}
      readonly={false}
      draft={false}
      onClose={() => {}}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  expect(screen.queryByRole("button", { name: "Complete" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  view.unmount();
});

test("mostra as text revisions da atividade (editar, apagar e adicionar)", async () => {
  api.get
    .mockResolvedValueOnce([]) // transitions
    .mockResolvedValueOnce([
      {
        id: 9,
        activity: 1,
        field: "notes",
        text_before: "nota velha",
        text_after: "nota nova",
        actor: { username: "alice" },
        created_at: "2026-01-02T00:00:00Z",
      },
      {
        id: 10,
        activity: 1,
        field: "notes",
        text_before: "nota nova",
        text_after: "",
        actor: { username: "alice" },
        created_at: "2026-01-03T00:00:00Z",
      },
      {
        id: 11,
        activity: 1,
        field: "description",
        text_before: "",
        text_after: "nova descrição",
        actor: { username: "alice" },
        created_at: "2026-01-05T00:00:00Z",
      },
      {
        id: 12,
        activity: 2,
        field: "description",
        text_before: "",
        text_after: "de outra atividade",
        actor: { username: "bob" },
        created_at: "2026-01-06T00:00:00Z",
      },
    ]);
  const { unmount } = renderDrawer(false);

  expect(await screen.findByText("− nota velha")).toBeInTheDocument();
  expect(screen.getByText("+ nota nova")).toBeInTheDocument();
  expect(screen.getByText("apagou")).toBeInTheDocument();
  expect(screen.getByText("adicionou")).toBeInTheDocument();
  expect(screen.getByText("+ nova descrição")).toBeInTheDocument();
  // revisões de outras atividades ficam de fora
  expect(screen.queryByText("de outra atividade")).not.toBeInTheDocument();
  unmount();
});

test("blocked é deletável em draft, mas não em execução", () => {
  const blockedActivity = { ...activity, status: "blocked", blocked_reason: "Waiting on prerequisites" };
  const renderWith = (draft) =>
    render(
      <ActivityDrawer
        open
        activity={blockedActivity}
        releaseSlug="r1"
        users={[]}
        githubOptions={{}}
        steps={[{ id: 1, label: "Step A" }]}
        activities={[blockedActivity]}
        readonly={false}
        draft={draft}
        canEdit={true}
        onClose={() => {}}
        onSave={() => {}}
        onDelete={() => {}}
        onMove={() => {}}
      />,
    );

  const draftView = renderWith(true);
  expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  draftView.unmount();

  const execView = renderWith(false);
  expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  execView.unmount();
});

test("Make a copy só aparece em modo de edição e chama onDuplicate", async () => {
  const onDuplicate = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <ActivityDrawer
      open
      activity={activity}
      releaseSlug="r1"
      users={[]}
      githubOptions={{}}
      steps={[{ id: 1, label: "Step A" }]}
      activities={[activity]}
      readonly={false}
      draft={true}
      canEdit={true}
      onClose={() => {}}
      onSave={() => {}}
      onDelete={() => {}}
      onDuplicate={onDuplicate}
      onMove={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Make a copy" }));
  await waitFor(() => expect(onDuplicate).toHaveBeenCalledWith(activity));
  view.unmount();

  renderDrawer(false, false);
  expect(screen.queryByRole("button", { name: "Make a copy" })).not.toBeInTheDocument();
});
