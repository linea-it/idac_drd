// O pivô: o plano é editável também em execução — o save sempre manda o
// payload estrutural completo. A única restrição de modo: status não muda em
// draft (a execução só começa após o gesto de start).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
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
      onClose={() => {}}
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );
  return { onSave, unmount: view.unmount };
}

test("em execução envia o payload estrutural completo", async () => {
  const { onSave } = renderDrawer(false);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
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

test("em in_review os objetivos aparecem como checklist e o Approve exige todos", async () => {
  const withObjectives = { ...activity, status: "in_review", objectives: "Validar schema\nGerar dataset" };
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

  // as duas metas aparecem no bloco de aprovação
  const approveButton = screen.getByRole("button", { name: "Approve" });
  expect(screen.getByText("Validar schema")).toBeInTheDocument();
  expect(screen.getByText("Gerar dataset")).toBeInTheDocument();

  // sem marcar tudo, Approve fica desabilitado
  expect(approveButton).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText("Validar schema"));
  expect(approveButton).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText("Gerar dataset"));
  expect(approveButton).toHaveProperty("disabled", false);
  fireEvent.click(approveButton);
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ status: "done" })));
  view.unmount();
});

test("em execução o status vira ação: Send to review em in_progress", async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
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
      onSave={onSave}
      onDelete={() => {}}
      onMove={() => {}}
    />,
  );

  // em in_progress: botão de entrega, sem Approve
  const sendButton = screen.getByRole("button", { name: "Send to review" });
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  fireEvent.click(sendButton);
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ status: "in_review" })));
  view.unmount();
});
