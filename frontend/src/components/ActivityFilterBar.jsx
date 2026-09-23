import {
  Autocomplete,
  Button,
  Chip,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo } from "react";
import { buildFilterOptions, EMPTY_FILTERS, isFilterActive } from "../activityFilters";
import { statusLabel } from "../activityStatus";

const MODE_LABELS = { manual: "Manual", nifi: "NiFi" };

// body2 = tipografia padrão secundária do board (0.875rem)
const BODY2 = { fontSize: "0.875rem" };

/**
 * Barra de filtros facetados (Assignee, Status, Mode, Area). Apenas derivação
 * visual: o estado (`filters`/`hideUnmatched`) vive em ReleaseBoard, que também
 * calcula `matched`/`total` para o texto "Showing N of M".
 */
export default function ActivityFilterBar({
  activities,
  filters,
  onChange,
  matched,
  total,
  showHideToggle = false,
  hideUnmatched = false,
  onHideUnmatched,
}) {
  // identidade estável das options (mesmo `activities` → mesmas listas)
  const options = useMemo(() => buildFilterOptions(activities), [activities]);
  const active = isFilterActive(filters);

  // o estado guarda ids; o Autocomplete de assignees trabalha com os objetos de option
  const assigneeValue = useMemo(
    () => options.assignees.filter((o) => filters.assignees?.includes(o.id)),
    [options, filters.assignees],
  );

  const setFacet = (key, value) => onChange({ ...filters, [key]: value });
  // Clear zera facets e o hide — evita hide órfão ao reaplicar filtro
  const clear = () => {
    onChange({ ...EMPTY_FILTERS });
    onHideUnmatched?.(false);
  };

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Facet
        label="Assignee"
        options={options.assignees}
        value={assigneeValue}
        onChange={(v) => setFacet("assignees", v.map((o) => o.id))}
        getOptionLabel={(o) => o.label}
        isOptionEqualToValue={(o, v) => o.id === v.id}
      />
      <Facet
        label="Status"
        options={options.statuses}
        value={filters.statuses ?? []}
        onChange={(v) => setFacet("statuses", v)}
        getOptionLabel={statusLabel}
      />
      <Facet
        label="Mode"
        options={options.modes}
        value={filters.modes ?? []}
        onChange={(v) => setFacet("modes", v)}
        getOptionLabel={(v) => MODE_LABELS[v] || v}
      />
      <Facet
        label="Area"
        options={options.areas}
        value={filters.areas ?? []}
        onChange={(v) => setFacet("areas", v)}
        getOptionLabel={(v) => v}
      />
      <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
        Showing {matched} of {total}
      </Typography>
      {active && (
        <Button size="small" aria-label="Clear filters" onClick={clear} sx={{ whiteSpace: "nowrap" }}>
          Clear
        </Button>
      )}
      {showHideToggle && (
        <FormControlLabel
          sx={{ ml: 1.5 }}
          control={
            <Switch
              size="small"
              checked={hideUnmatched}
              disabled={!active}
              onChange={(e) => onHideUnmatched?.(e.target.checked)}
            />
          }
          label="Hide Unmatched"
          slotProps={{ typography: { variant: "body2" } }}
        />
      )}
    </Stack>
  );
}

function Facet({ label, options, value, onChange, getOptionLabel, isOptionEqualToValue }) {
  return (
    <Autocomplete
      multiple
      size="small"
      limitTags={1}
      disableCloseOnSelect
      options={options}
      value={value}
      onChange={(_, v) => onChange(v)}
      getOptionLabel={getOptionLabel}
      isOptionEqualToValue={isOptionEqualToValue}
      renderTags={(tagValue, getTagProps) =>
        tagValue.map((option, index) => {
          const { key, ...tagProps } = getTagProps({ index });
          return (
            <Chip
              key={key}
              size="small"
              label={getOptionLabel(option)}
              {...tagProps}
              sx={{ height: 20, "& .MuiChip-label": { ...BODY2, px: 0.75 } }}
            />
          );
        })
      }
      renderOption={(props, option) => {
        const { key, ...optionProps } = props;
        return (
          <li key={key} {...optionProps}>
            <Typography variant="body2" component="span">
              {getOptionLabel(option)}
            </Typography>
          </li>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          size="small"
          InputLabelProps={{ ...params.InputLabelProps, sx: BODY2 }}
          inputProps={{ ...params.inputProps, style: { ...params.inputProps?.style, ...BODY2 } }}
        />
      )}
      sx={{
        minWidth: 140,
        "& .MuiInputBase-root": { ...BODY2, py: 0.25 },
        "& .MuiInputLabel-root": BODY2,
      }}
    />
  );
}
