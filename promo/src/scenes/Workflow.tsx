import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Appear, Caption, Kicker, Scene } from "../components/ui";
import { colors, fonts } from "../theme";

const STAGES = [
  { stage: "Read", tool: "LitKG", color: colors.litkg, note: "reading list → literature map" },
  { stage: "Write", tool: "you + your assistant", color: colors.text, note: "draft, cite, revise" },
  { stage: "Check", tool: "qalmsw", color: colors.qalmsw, note: "the paper's unit test" },
];

const CARD_W = 440;
const GAP = 120;
const LEFT = (1920 - (3 * CARD_W + 2 * GAP)) / 2;

export const Workflow: React.FC = () => {
  const frame = useCurrentFrame();
  const back = interpolate(frame, [95, 135], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const startX = LEFT + 2 * (CARD_W + GAP) + CARD_W / 2;
  const endX = LEFT + CARD_W / 2;
  const y = 640;
  const path = `M ${startX} ${y} C ${startX} ${y + 150}, ${endX} ${y + 150}, ${endX} ${y}`;
  const length = 1700;
  return (
    <Scene>
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 120 }}>
        <Appear>
          <div style={{ fontSize: 64, fontWeight: 800 }}>Two tools, one workflow</div>
        </Appear>
      </AbsoluteFill>
      {STAGES.map((s, i) => (
        <Appear key={s.stage} delay={15 + i * 18} style={{ position: "absolute", left: LEFT + i * (CARD_W + GAP), top: 330 }}>
          <div
            style={{
              width: CARD_W,
              height: 290,
              borderRadius: 24,
              background: colors.panel,
              border: `3px solid ${s.color === colors.text ? colors.panelEdge : s.color}`,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
              gap: 16,
            }}
          >
            <Kicker color={colors.muted}>{s.stage}</Kicker>
            <div style={{ fontSize: s.tool.length > 10 ? 40 : 62, fontWeight: 800, color: s.color, fontFamily: s.tool.length > 10 ? fonts.sans : fonts.mono }}>
              {s.tool}
            </div>
            <div style={{ fontSize: 28, color: colors.muted }}>{s.note}</div>
          </div>
        </Appear>
      ))}
      {[0, 1].map((i) => (
        <Appear key={i} delay={30 + i * 18} style={{ position: "absolute", left: LEFT + CARD_W + i * (CARD_W + GAP) + 28, top: 440 }}>
          <div style={{ fontSize: 64, color: colors.muted }}>→</div>
        </Appear>
      ))}
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        <path
          d={path}
          fill="none"
          stroke={colors.litkg}
          strokeWidth={5}
          strokeDasharray={length}
          strokeDashoffset={length * (1 - back)}
          strokeLinecap="round"
        />
      </svg>
      <div
        style={{
          position: "absolute",
          top: 790,
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: back,
          fontSize: 32,
          color: colors.litkg,
          fontWeight: 600,
        }}
      >
        qalmsw asks LitKG about every reference
      </div>
      <Caption delay={130}>Know the literature before you write. Test the paper before you submit.</Caption>
    </Scene>
  );
};
