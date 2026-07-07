import { describe, expect, it } from "vitest";
import { Terminal } from "@xterm/xterm";
import { Unicode11Addon } from "@xterm/addon-unicode11";

describe("xterm.js Unicode11Addon compatibility", () => {
  it("throws an error when loading the addon without allowProposedApi", () => {
    const term = new Terminal({
      allowProposedApi: false, // default
    });
    const addon = new Unicode11Addon();

    // It should throw because the addon uses proposed APIs
    expect(() => {
      term.loadAddon(addon);
    }).toThrow("You must set the allowProposedApi option to true to use proposed API");
  });

  it("successfully sets unicode.activeVersion when allowProposedApi is true", () => {
    const term = new Terminal({
      allowProposedApi: true,
    });
    const addon = new Unicode11Addon();
    term.loadAddon(addon);

    // This should not throw and should set the active version correctly
    expect(() => {
      term.unicode.activeVersion = "11";
    }).not.toThrow();
    
    expect(term.unicode.activeVersion).toBe("11");
  });
});
