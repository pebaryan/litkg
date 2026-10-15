# LitKG + qalmsw promo video

A 56-second, 1920×1080 promotional video built with [Remotion](https://www.remotion.dev/):
reading list → LitKG literature map → writing → qalmsw check (references verified by LitKG) →
benchmark → outro.

```bash
cd promo
npm install
npm run studio    # preview and scrub in the browser
npm run render    # out/litkg-qalmsw-promo.mp4
```

Scenes live in `src/scenes/`, shared styling in `src/theme.ts` and `src/components/ui.tsx`, and
scene order and lengths in `src/Promo.tsx`.

What is shown:
- The qalmsw output is a real run on LitKG's test manuscript (`tests/fixtures/paper`), shortened.
- The benchmark figures come from `benchmarks/results.json` (97.5% is shown rounded to 98%).
- The `litkg index` and `cited-by` output, and the graph, are an illustrative library in the real
  output format.

There is no soundtrack; add one with `<Audio>` in `src/Promo.tsx` (the asset must be licensed for reuse).
