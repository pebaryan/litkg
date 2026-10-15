import React from "react";
import { Composition } from "remotion";
import { Promo, PROMO_FRAMES } from "./Promo";
import { FPS } from "./theme";

export const RemotionRoot: React.FC = () => (
  <Composition id="Promo" component={Promo} durationInFrames={PROMO_FRAMES} fps={FPS} width={1920} height={1080} />
);
