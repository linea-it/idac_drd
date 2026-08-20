import { Autocomplete, Chip, ListSubheader, TextField, Typography } from "@mui/material";

// Combobox com chips: o padrão Material para muitos itens (Gmail/Contacts).
// Digita para filtrar; os escolhidos ficam visíveis e saem no X do chip.
export default function DependsOnField({ activities, value, onChange, disabled = false }) {
  const selected = activities.filter((a) => value.some((id) => Number(id) === Number(a.id)));
  const grouped = activities.some((a) => a.step_label);

  return (
    <Autocomplete
      multiple
      size="small"
      fullWidth
      disabled={disabled}
      options={activities}
      value={selected}
      onChange={(_, next) => onChange(next.map((a) => a.id))}
      getOptionLabel={(a) => a.label}
      isOptionEqualToValue={(a, b) => Number(a.id) === Number(b.id)}
      groupBy={grouped ? (a) => a.step_label || "Other" : undefined}
      renderGroup={(params) => (
        <li key={params.key}>
          <ListSubheader component="div" sx={{ fontWeight: 700, lineHeight: "32px", color: "text.primary" }}>
            {params.group}
          </ListSubheader>
          <ul style={{ padding: 0 }}>{params.children}</ul>
        </li>
      )}
      filterSelectedOptions
      disableCloseOnSelect
      renderTags={(tagValue, getTagProps) =>
        tagValue.map((option, index) => {
          const { key, ...tagProps } = getTagProps({ index });
          return <Chip key={key} size="small" label={option.label} {...tagProps} />;
        })
      }
      renderOption={(props, option) => {
        const { key, ...optionProps } = props;
        return (
          <li key={key} {...optionProps}>
            <Typography variant="body2" component="span">
              {option.label}
            </Typography>
          </li>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Depends on"
          placeholder={selected.length ? "" : "Search activities"}
        />
      )}
      sx={{ "& .MuiAutocomplete-inputRoot": { flexWrap: "wrap", gap: 0.5, py: 0.75 } }}
    />
  );
}
