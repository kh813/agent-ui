import type { Terminal } from "@xterm/xterm";

// Computes how many rows/cols fit in a given pixel content area. This
// deliberately does not use @xterm/addon-fit: that addon always reserves a
// flat 14px of width for an "overview ruler" scrollbar gutter, even when
// that addon isn't loaded and no such gutter is rendered - at a 13px
// monospace font that's roughly 2 columns narrower than what's really
// available, so a CLI that positions text via absolute column math (e.g.
// right-aligning against the terminal's reported width) ends up misaligned
// by about 2 characters from what's actually visible.
//
// The width/height passed in must come from the *observed container's own*
// committed layout box (e.g. a ResizeObserver entry's contentRect), never
// from re-measuring xterm's own rendered DOM after the fact - doing the
// latter created a feedback loop: resizing the terminal could nudge its
// rendered footprint, which the observer picked up as a fresh size, which
// produced an even larger computed size, growing without bound.
export function computeFitSize(
  term: Terminal,
  widthPx: number,
  heightPx: number
): { cols: number; rows: number } | null {
  const core = (term as unknown as { _core?: any })._core;
  const dimensions = core?._renderService?.dimensions;
  if (!dimensions || dimensions.css.cell.width === 0 || dimensions.css.cell.height === 0) return null;

  return {
    cols: Math.max(2, Math.floor(widthPx / dimensions.css.cell.width)),
    rows: Math.max(1, Math.floor(heightPx / dimensions.css.cell.height)),
  };
}
