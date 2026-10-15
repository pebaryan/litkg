import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Appear, Caption, Kicker, Pill, Scene, Typed, Window, typingFrames } from "../components/ui";
import { colors, fonts } from "../theme";

const TEX: { text: string; cite?: boolean }[] = [
  { text: "\\section{Introduction}" },
  { text: "Transformers~\\cite{vaswani2017attention} replaced", cite: true },
  { text: "recurrence with attention. Pre-training" },
  { text: "\\citep{devlin2019bert} and residual", cite: true },
  { text: "connections~\\cite{he2016deep} made them deep.", cite: true },
  { text: "Recent work~\\cite{smith2023quantum} suggests ...", cite: true },
];

export const Write: React.FC = () => (
  <Scene>
    <AbsoluteFill style={{ padding: "80px 90px" }}>
      <Appear>
        <Kicker color={colors.muted}>Write</Kicker>
        <div style={{ fontSize: 58, fontWeight: 800, marginTop: 10 }}>You draft. Your assistant helps. References pile up.</div>
      </Appear>
      <Appear delay={12} style={{ marginTop: 80, display: "flex", justifyContent: "center" }}>
        <Window title="main.tex" accent={colors.panelEdge} width={1360}>
          {TEX.map((line, i) => (
            <Appear key={line.text} delay={20 + i * 10} distance={8}>
              <div style={{ color: line.cite ? colors.text : colors.muted, fontSize: 36 }}>
                {line.text.split(/(\\cite[pt]?\{[^}]+\})/).map((part, j) =>
                  part.startsWith("\\cite") ? (
                    <span key={j} style={{ color: colors.qalmsw }}>
                      {part}
                    </span>
                  ) : (
                    <span key={j}>{part}</span>
                  ),
                )}
              </div>
            </Appear>
          ))}
        </Window>
      </Appear>
    </AbsoluteFill>
    <Caption delay={80}>Every citation is a claim that a real paper exists.</Caption>
  </Scene>
);

type Out = { severity: "error" | "info" | "dim"; where?: string; text: string; suggest?: string };

// Output of a real run on LitKG's test manuscript (tests/fixtures/paper), shortened.
const OUTPUT: Out[] = [
  { severity: "dim", text: "references: LitKG backend" },
  { severity: "dim", text: "running artifacts, figures, images, citations, references checkers" },
  { severity: "error", where: "main.tex:7 citations", text: "Cited key 'undefined2024' not found in bibliography." },
  {
    severity: "error",
    where: "refs.bib:19 references",
    text: "Reference 'devlin2019bert' (author-mismatch): listed authors not on the record: Brown, Michael; Lee, Sarah",
    suggest: 'Possible correct reference: "BERT: Pre-training of Deep Bidirectional Transformers…" Devlin, Jacob; Chang, Ming-Wei; Lee, Kenton et al. (2019) doi:10.18653/v1/n19-1423',
  },
  {
    severity: "error",
    where: "refs.bib:26 references",
    text: "Reference 'smith2023quantum' (doi-not-found): DOI 10.5555/jmlr.2023.99999 does not exist",
  },
  { severity: "info", where: "refs.bib:19 references", text: "Reference 'devlin2019bert' (missing-doi): add doi = {10.18653/v1/n19-1423}" },
];

const CMD = "qalmsw check --library .litkg_store.ttl main.tex";

export const Check: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const typed = 15 + typingFrames(CMD, fps) + 10;
  const lineAt = (i: number) => typed + i * (i < 2 ? 12 : 38);
  const done = lineAt(OUTPUT.length) + 10;
  const color = { error: colors.error, info: colors.info, dim: colors.muted };

  return (
    <Scene>
      <AbsoluteFill style={{ padding: "70px 90px" }}>
        <Appear>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
            <div>
              <Kicker color={colors.qalmsw}>Check · qalmsw</Kicker>
              <div style={{ fontSize: 58, fontWeight: 800, marginTop: 10 }}>Run the paper's unit test</div>
            </div>
            <div style={{ display: "flex", gap: 14, paddingBottom: 10 }}>
              <Pill color={colors.qalmsw}>artifacts</Pill>
              <Pill color={colors.qalmsw}>figures</Pill>
              <Pill color={colors.qalmsw}>citations</Pill>
              <Pill color={colors.litkg}>references ← LitKG</Pill>
              <Pill color={colors.muted}>grammar · claims (LLM)</Pill>
            </div>
          </div>
        </Appear>
        <Appear delay={6} style={{ marginTop: 40 }}>
          <Window title="~/thesis" accent={colors.qalmsw} width={1740}>
            <div>
              <span style={{ color: colors.qalmsw }}>$ </span>
              <Typed text={CMD} start={15} cursor={frame < typed} />
            </div>
            {OUTPUT.map((line, i) =>
              frame >= lineAt(i) ? (
                <Appear key={i} delay={lineAt(i)} distance={6}>
                  <div style={{ marginTop: line.severity === "dim" ? 0 : 14, fontSize: 24 }}>
                    {line.severity !== "dim" && (
                      <span style={{ color: color[line.severity], fontWeight: 700 }}>{line.severity} </span>
                    )}
                    {line.where && <span style={{ color: colors.muted }}>{line.where} </span>}
                    <span style={{ color: line.severity === "dim" ? colors.muted : colors.text }}>{line.text}</span>
                    {line.suggest && (
                      <div style={{ color: colors.ok, paddingLeft: 32 }}>suggest: {line.suggest}</div>
                    )}
                  </div>
                </Appear>
              ) : null,
            )}
            {frame >= done && (
              <Appear delay={done} distance={6}>
                <div style={{ marginTop: 18, fontFamily: fonts.mono, color: colors.error, fontWeight: 700 }}>
                  4 issue(s) · exit 1
                </div>
              </Appear>
            )}
          </Window>
        </Appear>
      </AbsoluteFill>
      <Caption delay={done + 10}>Invented authors and an invented DOI: caught, with the correct record suggested.</Caption>
    </Scene>
  );
};
