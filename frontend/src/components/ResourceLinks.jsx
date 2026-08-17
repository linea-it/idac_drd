import LinkIcon from "@mui/icons-material/Link";
import { IconButton, Menu, MenuItem, Tooltip } from "@mui/material";
import { useState } from "react";

// Ícone de link para resources (links de documentação/instruções) de um step
// ou activity. Um recurso → abre direto (tooltip com o label); vários → menu.
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

export default function ResourceLinks({ resources, size = "small", sx }) {
  const [anchor, setAnchor] = useState(null);
  const list = (resources || []).filter((r) => isSafeUrl(r?.url));
  if (!list.length) return null;

  function open(e, res) {
    // para uso dentro de CardActionArea: não deixa o clique selecionar o card
    e?.stopPropagation();
    window.open(res.url, "_blank", "noopener,noreferrer");
  }

  if (list.length === 1) {
    const only = list[0];
    return (
      <Tooltip title={linkLabel(only)}>
        <IconButton size={size} sx={sx} onClick={(e) => open(e, only)}>
          <LinkIcon fontSize={size === "small" ? "small" : "inherit"} />
        </IconButton>
      </Tooltip>
    );
  }
  return (
    <>
      <IconButton size={size} sx={sx} onClick={(e) => {
        e?.stopPropagation();
        setAnchor(e.currentTarget);
      }}>
        <LinkIcon fontSize={size === "small" ? "small" : "inherit"} />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {list.map((r, i) => (
          <MenuItem key={i} onClick={(e) => { setAnchor(null); open(e, r); }}>
            {linkLabel(r)}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
