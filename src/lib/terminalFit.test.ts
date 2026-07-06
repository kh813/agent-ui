import { describe, expect, it } from "vitest";
import type { Terminal } from "@xterm/xterm";
import { computeFitSize } from "./terminalFit";

function fakeTerminal(cellWidth: number, cellHeight: number): Terminal {
  return {
    _core: {
      _renderService: {
        dimensions: {
          css: {
            cell: { width: cellWidth, height: cellHeight },
          },
        },
      },
    },
  } as unknown as Terminal;
}

describe("computeFitSize", () => {
  it("floors the pixel area down to whole cells", () => {
    // 100px / 8px = 12.5 cols -> floors to 12; 50px / 16px = 3.125 rows -> floors to 3
    expect(computeFitSize(fakeTerminal(8, 16), 100, 50)).toEqual({ cols: 12, rows: 3 });
  });

  it("does not reserve extra width for a scrollbar gutter (unlike @xterm/addon-fit)", () => {
    // @xterm/addon-fit would subtract a flat 14px before dividing; this
    // implementation must use the full width so a 300px-wide container at a
    // 1px cell width fits exactly 300 columns, not ~286.
    expect(computeFitSize(fakeTerminal(1, 1), 300, 40)).toEqual({ cols: 300, rows: 40 });
  });

  it("clamps to a minimum of 2 columns and 1 row for a tiny or collapsed container", () => {
    expect(computeFitSize(fakeTerminal(10, 20), 5, 5)).toEqual({ cols: 2, rows: 1 });
    expect(computeFitSize(fakeTerminal(10, 20), 0, 0)).toEqual({ cols: 2, rows: 1 });
  });

  it("returns null when xterm hasn't measured its cell size yet", () => {
    expect(computeFitSize(fakeTerminal(0, 0), 100, 100)).toBeNull();

    const noRenderService = { _core: {} } as unknown as Terminal;
    expect(computeFitSize(noRenderService, 100, 100)).toBeNull();
  });
});
