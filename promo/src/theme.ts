import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

const inter = loadInter("normal", { weights: ["400", "600", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "700"], subsets: ["latin"] });

export const FPS = 30;

export const fonts = {
  sans: inter.fontFamily,
  mono: mono.fontFamily,
};

export const colors = {
  bg: "#0b1020",
  panel: "#121a30",
  panelEdge: "#1f2a48",
  text: "#e6ebf5",
  muted: "#8b97b3",
  litkg: "#2dd4bf",
  qalmsw: "#fbbf24",
  error: "#f87171",
  warning: "#fb923c",
  info: "#60a5fa",
  ok: "#4ade80",
};
