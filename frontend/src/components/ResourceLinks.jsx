import AddIcon from "@mui/icons-material/Add";
import AddLinkIcon from "@mui/icons-material/AddLink";
import LinkIcon from "@mui/icons-material/Link";
import { Button, Divider, IconButton, ListItemIcon, Menu, MenuItem, Popover, Stack, TextField, Tooltip, Typography } from "@mui/material";
import { useRef, useState } from "react";

// Ícone de link para resources (links de documentação/instruções) de um step
// ou activity. Sem links e com onAdd → ícone "+". Com links → menu; "Add link"
// é o último item. Sem onAdd: um recurso abre direto, vários abrem o menu.
// Apenas URLs http(s) são renderizadas (o backend valida, isto é defesa extra).

const isSafeUrl = (url) => /^https?:\/\//i.test(url || "");

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function linkLabel(res) {
  return (res?.label || "").trim() || hostOf(res?.url);
}

function AddLinkPopover({ open, anchorEl, onClose, onAdd, count, pending }) {
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [addError, setAddError] = useState("");

  function close() {
    setLabel("");
    setUrl("");
    setAddError("");
    onClose();
  }

  async function submitAdd(e) {
    e.preventDefault();
    e.stopPropagation();
    const nextUrl = url.trim();
    if (!isSafeUrl(nextUrl)) {
      setAddError("Link URLs need to start with http:// or https://.");
      return;
    }
    if (count >= 10) {
      setAddError("You can add up to 10 links.");
      return;
    }
    setAddError("");
    try {
      await onAdd({ label: label.trim(), url: nextUrl });
      close();
    } catch (err) {
      setAddError(err?.message || "Could not add the link.");
    }
  }

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={close}
      onClick={(e) => e.stopPropagation()}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
    >
      <form onSubmit={submitAdd}>
        <Stack spacing={1.5} sx={{ p: 2, width: 280 }}>
          <Typography variant="subtitle2">Add link</Typography>
          <TextField
            size="small"
            label="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            autoFocus
            fullWidth
          />
          <TextField
            size="small"
            label="URL"
            placeholder="https://docs.google.com/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            fullWidth
            error={Boolean(addError)}
            helperText={addError || " "}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={close} disabled={pending}>
              Cancel
            </Button>
            <Button size="small" type="submit" variant="contained" disabled={pending || !url.trim()}>
              Add
            </Button>
          </Stack>
        </Stack>
      </form>
    </Popover>
  );
}

export default function ResourceLinks({ resources, size = "small", sx, onAdd, pending = false }) {
  const buttonRef = useRef(null);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [adding, setAdding] = useState(false);
  const list = (resources || []).filter((r) => isSafeUrl(r?.url));
  const iconSize = size === "small" ? "small" : "inherit";

  function openLink(e, res) {
    e?.stopPropagation();
    window.open(res.url, "_blank", "noopener,noreferrer");
  }

  function openAdd() {
    setMenuAnchor(null);
    setAdding(true);
  }

  if (!list.length) {
    if (!onAdd) return null;
    return (
      <>
        <Tooltip title="Add link">
          <span>
            <IconButton
              ref={buttonRef}
              size={size}
              sx={sx}
              aria-label="Add link"
              disabled={pending}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setAdding(true);
              }}
            >
              <AddLinkIcon fontSize={iconSize} />
            </IconButton>
          </span>
        </Tooltip>
        <AddLinkPopover
          open={adding}
          anchorEl={buttonRef.current}
          onClose={() => setAdding(false)}
          onAdd={onAdd}
          count={list.length}
          pending={pending}
        />
      </>
    );
  }

  if (list.length === 1 && !onAdd) {
    const only = list[0];
    return (
      <Tooltip title={linkLabel(only)}>
        <IconButton size={size} sx={sx} onMouseDown={(e) => e.stopPropagation()} onClick={(e) => openLink(e, only)}>
          <LinkIcon fontSize={iconSize} />
        </IconButton>
      </Tooltip>
    );
  }

  return (
    <>
      <IconButton
        ref={buttonRef}
        size={size}
        sx={sx}
        aria-label="Links"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          setMenuAnchor(e.currentTarget);
        }}
      >
        <LinkIcon fontSize={iconSize} />
      </IconButton>
      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
        {list.map((r, i) => (
          <MenuItem key={i} onClick={(e) => { setMenuAnchor(null); openLink(e, r); }}>
            {linkLabel(r)}
          </MenuItem>
        ))}
        {onAdd && <Divider />}
        {onAdd && (
          <MenuItem
            onClick={(e) => {
              e.stopPropagation();
              openAdd();
            }}
            disabled={pending}
            sx={{
              color: "primary.main",
              fontWeight: 500,
              "&.Mui-disabled": { color: "text.disabled" },
            }}
          >
            <ListItemIcon sx={{ color: "inherit", minWidth: 32 }}>
              <AddIcon fontSize="small" />
            </ListItemIcon>
            New
          </MenuItem>
        )}
      </Menu>
      {onAdd && (
        <AddLinkPopover
          open={adding}
          anchorEl={buttonRef.current}
          onClose={() => setAdding(false)}
          onAdd={onAdd}
          count={list.length}
          pending={pending}
        />
      )}
    </>
  );
}
