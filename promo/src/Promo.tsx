import React from "react";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { Check, Write } from "./scenes/Check";
import { Hook, Problem } from "./scenes/Intro";
import { LitKGScene } from "./scenes/LitKG";
import { Benchmark, Fade, Outro } from "./scenes/Outro";
import { Workflow } from "./scenes/Workflow";

const TRANSITION = 15;

const SCENES: { id: string; frames: number; component: React.FC; enter?: "slide" }[] = [
  { id: "hook", frames: 120, component: Hook },
  { id: "problem", frames: 195, component: Problem },
  { id: "workflow", frames: 195, component: Workflow },
  { id: "litkg", frames: 330, component: LitKGScene, enter: "slide" },
  { id: "write", frames: 150, component: Write, enter: "slide" },
  { id: "check", frames: 420, component: Check, enter: "slide" },
  { id: "benchmark", frames: 210, component: Benchmark },
  { id: "outro", frames: 180, component: Outro },
];

export const PROMO_FRAMES = SCENES.reduce((sum, s) => sum + s.frames, 0) - TRANSITION * (SCENES.length - 1);

export const Promo: React.FC = () => (
  <TransitionSeries>
    {SCENES.flatMap((scene, i) => {
      const Component = scene.component;
      const parts = [];
      if (i > 0) {
        parts.push(
          <TransitionSeries.Transition
            key={`${scene.id}-in`}
            presentation={scene.enter === "slide" ? slide({ direction: "from-right" }) : fade()}
            timing={linearTiming({ durationInFrames: TRANSITION })}
          />,
        );
      }
      parts.push(
        <TransitionSeries.Sequence key={scene.id} durationInFrames={scene.frames}>
          {i === SCENES.length - 1 ? (
            <Fade frames={scene.frames}>
              <Component />
            </Fade>
          ) : (
            <Component />
          )}
        </TransitionSeries.Sequence>,
      );
      return parts;
    })}
  </TransitionSeries>
);
