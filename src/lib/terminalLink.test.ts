import { describe, expect, it, vi } from "vitest";
import { Terminal } from "@xterm/xterm";
import { WebLinksAddon } from "@xterm/addon-web-links";

describe("xterm.js WebLinksAddon integration", () => {
  it("successfully loads WebLinksAddon with a custom click handler", () => {
    const term = new Terminal({ allowProposedApi: true });
    
    // Custom click handler signature matches (_event, uri) -> void
    const mockHandler = vi.fn();
    const addon = new WebLinksAddon(mockHandler);
    
    expect(() => {
      term.loadAddon(addon);
    }).not.toThrow();
  });
});
