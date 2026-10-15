import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, fonts } from "../theme";

/** Fades and lifts its children in, starting at `delay` frames. */
export const Appear: React.FC<{ delay?: number; distance?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({
  delay = 0,
  distance = 24,
  style,
  children,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return (
    <div style={{ opacity: progress, transform: `translateY(${(1 - progress) * distance}px)`, ...style }}>{children}</div>
  );
};

export const Scene: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <AbsoluteFill
    style={{
      backgroundColor: colors.bg,
      backgroundImage: `radial-gradient(circle at 20% 15%, ${colors.litkg}14, transparent 45%), radial-gradient(circle at 85% 90%, ${colors.qalmsw}12, transparent 45%)`,
      color: colors.text,
      fontFamily: fonts.sans,
      ...style,
    }}
  >
    {children}
  </AbsoluteFill>
);

export const Caption: React.FC<{ children: React.ReactNode; delay?: number }> = ({ children, delay = 0 }) => (
  <Appear delay={delay} style={{ position: "absolute", left: 0, right: 0, bottom: 70, textAlign: "center" }}>
    <span style={{ fontSize: 38, color: colors.muted, fontWeight: 400 }}>{children}</span>
  </Appear>
);

export const Kicker: React.FC<{ color: string; children: React.ReactNode }> = ({ color, children }) => (
  <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 6, textTransform: "uppercase", color }}>{children}</div>
);

/** Text typed out character by character from `start`, at `cps` characters per second. */
export const Typed: React.FC<{ text: string; start?: number; cps?: number; cursor?: boolean }> = ({
  text,
  start = 0,
  cps = 28,
  cursor = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const count = Math.max(0, Math.floor(((frame - start) / fps) * cps));
  const shown = text.slice(0, count);
  const typing = count > 0 && count < text.length;
  const blink = Math.floor(frame / 15) % 2 === 0;
  return (
    <span>
      {shown}
      {cursor && (typing || (count >= text.length && blink)) ? <span style={{ opacity: 0.8 }}>▍</span> : null}
    </span>
  );
};

/** Frames needed to type `text` at `cps`. */
export const typingFrames = (text: string, fps: number, cps = 28) => Math.ceil((text.length / cps) * fps);

export const Window: React.FC<{
  title: string;
  accent: string;
  width: number;
  height?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ title, accent, width, height, children, style }) => (
  <div
    style={{
      width,
      height,
      background: colors.panel,
      border: `2px solid ${colors.panelEdge}`,
      borderRadius: 18,
      boxShadow: `0 30px 80px rgba(0,0,0,0.45), 0 0 0 1px ${accent}22`,
      overflow: "hidden",
      ...style,
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "14px 20px",
        borderBottom: `2px solid ${colors.panelEdge}`,
        background: "#0e1528",
      }}
    >
      {["#f87171", "#fbbf24", "#4ade80"].map((c) => (
        <div key={c} style={{ width: 14, height: 14, borderRadius: 7, background: c, opacity: 0.85 }} />
      ))}
      <div style={{ marginLeft: 14, fontFamily: fonts.mono, fontSize: 20, color: colors.muted }}>{title}</div>
    </div>
    <div style={{ padding: "22px 28px", fontFamily: fonts.mono, fontSize: 25, lineHeight: 1.55 }}>{children}</div>
  </div>
);

export const Pill: React.FC<{ color: string; children: React.ReactNode; style?: React.CSSProperties }> = ({
  color,
  children,
  style,
}) => (
  <span
    style={{
      display: "inline-block",
      padding: "4px 14px",
      borderRadius: 999,
      border: `2px solid ${color}`,
      color,
      fontWeight: 700,
      fontSize: 22,
      ...style,
    }}
  >
    {children}
  </span>
);

/** 0 → 1 between `from` and `to` frames, clamped. */
export const useProgress = (from: number, to: number) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [from, to], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};
