import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Appear, Caption, Kicker, Scene, Typed, Window, typingFrames } from "../components/ui";
import { colors } from "../theme";

type Node = { id: string; label: string; year: number; x: number; y: number; read: boolean };

const NODES: Node[] = [
  { id: "attn", label: "Attention Is All You Need", year: 2017, x: 320, y: 310, read: true },
  { id: "bert", label: "BERT", year: 2019, x: 110, y: 90, read: true },
  { id: "gpt3", label: "Language Models are Few-Shot Learners", year: 2020, x: 560, y: 60, read: false },
  { id: "vit", label: "An Image is Worth 16x16 Words", year: 2021, x: 720, y: 280, read: false },
  { id: "resnet", label: "Deep Residual Learning", year: 2016, x: 730, y: 540, read: true },
  { id: "ln", label: "Layer Normalization", year: 2016, x: 100, y: 500, read: false },
  { id: "adam", label: "Adam", year: 2015, x: 420, y: 590, read: true },
];

const EDGES: [string, string][] = [
  ["bert", "attn"],
  ["gpt3", "attn"],
  ["vit", "attn"],
  ["vit", "resnet"],
  ["attn", "ln"],
  ["attn", "adam"],
  ["resnet", "adam"],
];

const CMD1 = "litkg index ./reading";
const OUT1 = "Indexed 9 file(s) into .litkg_store.ttl: 7 paper(s), 1 bibliography (6 entries), 1 reading list(s).";
const CMD2 = "litkg cited-by \"Attention Is All You Need\"";
const OUT2 = ["BERT (2019)", "Language Models are Few-Shot Learners (2020)", "An Image is Worth 16x16 Words (2021)"];

const GRAPH_START = 70;

export const LitKGScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t1 = 10;
  const o1 = t1 + typingFrames(CMD1, fps) + 8;
  const t2 = o1 + 60;
  const o2 = t2 + typingFrames(CMD2, fps) + 8;
  const at = (id: string) => NODES.find((n) => n.id === id)!;
  const nodeDelay = (i: number) => GRAPH_START + i * 9;
  const nodeIndex = (id: string) => NODES.findIndex((n) => n.id === id);

  return (
    <Scene>
      <AbsoluteFill style={{ padding: "80px 90px" }}>
        <Appear>
          <Kicker color={colors.litkg}>Read · LitKG</Kicker>
          <div style={{ fontSize: 58, fontWeight: 800, marginTop: 10 }}>Your reading list becomes a literature map</div>
        </Appear>
        <div style={{ display: "flex", gap: 50, marginTop: 50, alignItems: "flex-start" }}>
          <Appear delay={5}>
            <Window title="~/thesis" accent={colors.litkg} width={830} height={560}>
              <div>
                <span style={{ color: colors.litkg }}>$ </span>
                <Typed text={CMD1} start={t1} cursor={frame < o1} />
              </div>
              {frame >= o1 && <div style={{ color: colors.muted, whiteSpace: "normal" }}>{OUT1}</div>}
              {frame >= t2 && (
                <div style={{ marginTop: 18 }}>
                  <span style={{ color: colors.litkg }}>$ </span>
                  <Typed text={CMD2} start={t2} />
                </div>
              )}
              {OUT2.map((line, i) =>
                frame >= o2 + i * 6 ? (
                  <div key={line} style={{ color: colors.text }}>
                    <span style={{ color: colors.litkg }}>• </span>
                    {line}
                  </div>
                ) : null,
              )}
            </Window>
          </Appear>
          <svg width={900} height={700} style={{ overflow: "visible", marginTop: -40 }}>
            {EDGES.map(([from, to]) => {
              const a = at(from);
              const b = at(to);
              const start = Math.max(nodeDelay(nodeIndex(from)), nodeDelay(nodeIndex(to))) + 8;
              const p = interpolate(frame, [start, start + 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
              return (
                <line
                  key={`${from}-${to}`}
                  x1={a.x}
                  y1={a.y}
                  x2={a.x + (b.x - a.x) * p}
                  y2={a.y + (b.y - a.y) * p}
                  stroke={colors.litkg}
                  strokeOpacity={0.45}
                  strokeWidth={3}
                />
              );
            })}
            {NODES.map((n, i) => {
              const s = spring({ frame: frame - nodeDelay(i), fps, config: { damping: 14, mass: 0.6 } });
              const highlight = n.id === "attn" && frame >= o2 ? 1 : 0;
              return (
                <g key={n.id} transform={`translate(${n.x} ${n.y}) scale(${s})`}>
                  <circle
                    r={n.id === "attn" ? 30 : 22}
                    fill={n.read ? colors.litkg : colors.bg}
                    stroke={colors.litkg}
                    strokeWidth={highlight ? 7 : 4}
                  />
                  <text y={n.id === "attn" ? 62 : 52} textAnchor="middle" fill={colors.text} fontSize={22} fontWeight={600} stroke={colors.bg} strokeWidth={8} paintOrder="stroke">
                    {n.label}
                  </text>
                  <text y={n.id === "attn" ? 88 : 78} textAnchor="middle" fill={colors.muted} fontSize={19} stroke={colors.bg} strokeWidth={8} paintOrder="stroke">
                    {n.year}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </AbsoluteFill>
      <Caption delay={200}>PDFs, BibTeX and reading lists in one local RDF graph. Query it, chart it, export it.</Caption>
    </Scene>
  );
};
