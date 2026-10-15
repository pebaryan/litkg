import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Appear, Caption, Scene } from "../components/ui";
import { colors, fonts } from "../theme";

export const Hook: React.FC = () => (
  <Scene>
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", textAlign: "center" }}>
      <Appear delay={5}>
        <div style={{ fontSize: 84, fontWeight: 800 }}>Your paper cites 60 references.</div>
      </Appear>
      <Appear delay={40} style={{ marginTop: 28 }}>
        <div style={{ fontSize: 84, fontWeight: 800, color: colors.qalmsw }}>Are they all real?</div>
      </Appear>
    </AbsoluteFill>
  </Scene>
);

const PROBLEMS = [
  { label: "Invented DOI", detail: "doi.org has never heard of it" },
  { label: "Real DOI, wrong paper", detail: "it resolves, to something else" },
  { label: "Real title, invented authors", detail: "looks right, cites nobody" },
];

const BIB_LINES: { text: string; bad?: boolean }[] = [
  { text: "@inproceedings{devlin2019bert," },
  { text: "  title  = {BERT: Pre-training of Deep Bidirectional" },
  { text: "            Transformers for Language Understanding}," },
  { text: "  author = {Brown, Michael and Lee, Sarah},", bad: true },
  { text: "  year   = {2019}," },
  { text: "}" },
];

export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const glow = interpolate(frame, [45, 60], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Scene>
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 70, paddingBottom: 60 }}>
        <Appear delay={0}>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 28,
              lineHeight: 1.6,
              background: colors.panel,
              border: `2px solid ${colors.panelEdge}`,
              borderRadius: 18,
              padding: "30px 38px",
              width: 990,
            }}
          >
            {BIB_LINES.map((line) => (
              <div
                key={line.text}
                style={{
                  color: line.bad ? colors.text : colors.muted,
                  background: line.bad ? `rgba(248,113,113,${0.18 * glow})` : undefined,
                  borderLeft: line.bad ? `5px solid rgba(248,113,113,${glow})` : "5px solid transparent",
                  paddingLeft: 12,
                  marginLeft: -17,
                  whiteSpace: "pre",
                }}
              >
                {line.text}
              </div>
            ))}
          </div>
        </Appear>
        <div style={{ display: "flex", flexDirection: "column", gap: 34 }}>
          {PROBLEMS.map((p, i) => (
            <Appear key={p.label} delay={30 + i * 22} distance={0} style={{ transform: "none" }}>
              <div style={{ borderLeft: `6px solid ${colors.error}`, paddingLeft: 24 }}>
                <div style={{ fontSize: 44, fontWeight: 800 }}>{p.label}</div>
                <div style={{ fontSize: 30, color: colors.muted, marginTop: 4 }}>{p.detail}</div>
              </div>
            </Appear>
          ))}
        </div>
      </AbsoluteFill>
      <Caption delay={100}>AI-assisted writing makes these easy to produce, and hard to spot.</Caption>
    </Scene>
  );
};
