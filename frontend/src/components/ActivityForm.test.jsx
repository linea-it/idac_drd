// Add activity: o formulário aceita múltiplas dependências (depends_on_ids é
// lista, como no backend e no editor de templates).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import ActivityForm from "./ActivityForm";

const activities = [
  { id: 1, label: "Step 1", step: 1 },
  { id: 2, label: "Step 2", step: 1 },
  { id: 3, label: "Step 3", step: 1 },
];

function renderForm() {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <ActivityForm
      open
      steps={[{ id: 1, label: "Step A" }]}
      activities={activities}
      onClose={() => {}}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

test("add activity permite duas ou mais dependências", async () => {
  const onSubmit = renderForm();
  // o label do campo required termina com o asterisco do MUI ("Label *")
  fireEvent.change(screen.getByLabelText(/Label/), { target: { value: "New activity" } });
  // o combobox "Depends on" é o terceiro (Step, After, Depends on)
  const dependsSelect = screen.getAllByRole("combobox")[2];
  fireEvent.mouseDown(dependsSelect);
  fireEvent.click(screen.getByRole("option", { name: "Step 1" }));
  fireEvent.click(screen.getByRole("option", { name: "Step 3" }));
  // fecha o menu via click-away (o Popover fecha com mousedown fora do Paper)
  const backdrops = document.querySelectorAll(".MuiBackdrop-root");
  fireEvent.mouseDown(backdrops[backdrops.length - 1]);
  fireEvent.click(backdrops[backdrops.length - 1]);
  // o menu aberto deixa o dialog aria-hidden; espera o unmount antes do Add
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ label: "New activity", depends_on_ids: [1, 3] }),
  );
});
