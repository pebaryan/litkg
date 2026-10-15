import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Appear, Caption, Kicker, Scene } from "../components/ui";
import { colors, fonts } from "../theme";

// From benchmarks/results.json: 40 Crossref journal articles × 6 cases, live registries.
const STATS = [
  { value: 100, suffix: "%", label: "nonexistent DOIs caught", color: colors.error },
  { value: 100, suffix: "%", label: "DOIs of the wrong paper caught", color: colors.error },
  { value: 98, suffix: "%", label: "invented author lists caught", color: colors.warning },
  { value: 0, suffix: "", label: "false failures on 80 real references", color: colors.ok },
];

export const Benchmark: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene>
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 110 }}>
        <Appear>
          <Kicker color={colors.litkg}>Measured, not promised</Kicker>
        </Appear>
        <Appear delay={6} style={{ marginTop: 14 }}>
          <div style={{ fontSize: 58, fontWeight: 800 }}>Fabrication benchmark against live registries</div>
        </Appear>
        <div style={{ display: "flex", gap: 40, marginTop: 110 }}>
          {STATS.map((s, i) => {
            const start = 25 + i * 15;
            const shown = Math.round(
              interpolate(frame, [start, start + 35], [0, s.value], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            );
            return (
              <Appear key={s.label} delay={start}>
                <div
                  style={{
                    width: 380,
                    height: 330,
                    borderRadius: 24,
                    background: colors.panel,
                    border: `2px solid ${colors.panelEdge}`,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    textAlign: "center",
                    padding: 24,
                  }}
                >
                  <div style={{ fontSize: 120, fontWeight: 800, color: s.color, fontFamily: fonts.mono }}>
                    {shown}
                    {s.suffix}
                  </div>
                  <div style={{ fontSize: 30, color: colors.text, marginTop: 10 }}>{s.label}</div>
                </div>
              </Appear>
            );
          })}
        </div>
      </AbsoluteFill>
      <Caption delay={110}>40 Crossref journal articles × 6 real and fabricated variants. Rerun it yourself.</Caption>
    </Scene>
  );
};

export const Outro: React.FC = () => (
  <Scene>
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", textAlign: "center" }}>
      <Appear>
        <div style={{ fontSize: 76, fontWeight: 800 }}>From reading list to submission</div>
      </Appear>
      <div style={{ display: "flex", gap: 120, marginTop: 80 }}>
        <Appear delay={15}>
          <Kicker color={colors.muted}>Read</Kicker>
          <div style={{ fontSize: 88, fontWeight: 800, fontFamily: fonts.mono, color: colors.litkg, marginTop: 8 }}>LitKG</div>
          <div style={{ fontSize: 30, color: colors.muted, fontFamily: fonts.mono, marginTop: 10 }}>github.com/pebaryan/litkg</div>
        </Appear>
        <Appear delay={28}>
          <Kicker color={colors.muted}>Check</Kicker>
          <div style={{ fontSize: 88, fontWeight: 800, fontFamily: fonts.mono, color: colors.qalmsw, marginTop: 8 }}>qalmsw</div>
          <div style={{ fontSize: 30, color: colors.muted, fontFamily: fonts.mono, marginTop: 10 }}>github.com/pebaryan/qalmsw</div>
        </Appear>
      </div>
    </AbsoluteFill>
    <Caption delay={50}>Local-first: registries see identifiers and titles, never your manuscript.</Caption>
  </Scene>
);

export const Fade: React.FC<{ children: React.ReactNode; frames: number }> = ({ children, frames }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [frames - 20, frames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};
