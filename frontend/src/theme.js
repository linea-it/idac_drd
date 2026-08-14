import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#0989cb",
      dark: "#31297f",
    },
    text: {
      primary: "rgba(14,28,50,0.87)",
      secondary: "rgba(14,28,50,0.6)",
      disabled: "rgba(14,28,50,0.38)",
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
  shape: {
    borderRadius: 8,
  },
});

export default theme;
