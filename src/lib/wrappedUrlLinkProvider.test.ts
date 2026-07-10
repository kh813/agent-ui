import { describe, expect, it, vi } from "vitest";
import { Terminal } from "@xterm/xterm";
import { registerWrappedUrlLinkProvider } from "./wrappedUrlLinkProvider";

function write(term: Terminal, data: string): Promise<void> {
  return new Promise((resolve) => term.write(data, resolve));
}

// Captures the ILinkProvider registered on the terminal so tests can query
// provideLinks() directly instead of simulating real mouse events.
function captureProvider(term: Terminal) {
  let captured: { provideLinks: (y: number, cb: (links: unknown[] | undefined) => void) => void } | null = null;
  const original = term.registerLinkProvider.bind(term);
  term.registerLinkProvider = ((provider: any) => {
    captured = provider;
    return original(provider);
  }) as typeof term.registerLinkProvider;
  return () => captured!;
}

async function findLinks(term: Terminal, row: number): Promise<any[]> {
  const provider = captureProvider(term);
  registerWrappedUrlLinkProvider(term, vi.fn());
  return new Promise((resolve) => provider().provideLinks(row, (links) => resolve(links ?? [])));
}

describe("registerWrappedUrlLinkProvider", () => {
  it("detects a URL that fits on a single row", async () => {
    const term = new Terminal({ cols: 40, rows: 5, allowProposedApi: true });
    const url = "https://example.com/short";
    await write(term, url);

    const links = await findLinks(term, 1);
    expect(links.map((l) => l.text)).toEqual([url]);
  });

  it("detects a URL that soft-wraps across rows via xterm's own auto-wrap", async () => {
    const term = new Terminal({ cols: 20, rows: 5, allowProposedApi: true });
    const url = "https://example.com/some/very/long/path/that/exceeds/twenty/columns";
    await write(term, url);

    expect(term.buffer.active.getLine(1)?.isWrapped).toBe(true);

    const links = await findLinks(term, 2);
    expect(links.map((l) => l.text)).toEqual([url]);
  });

  it("detects a URL hard-wrapped by the program itself (no isWrapped flag)", async () => {
    const term = new Terminal({ cols: 20, rows: 5, allowProposedApi: true });
    // Simulate a CLI/TUI that wraps its own long tokens with a real newline
    // once a row is full, instead of relying on terminal auto-wrap - the
    // continuation row is never flagged `isWrapped` in this case.
    const url = "https://example.com/some/very/long/path/that/exceeds/twenty/columns";
    const first = url.slice(0, 20);
    const rest = url.slice(20);
    await write(term, `${first}\r\n${rest}`);

    expect(term.buffer.active.getLine(1)?.isWrapped).toBe(false);

    const links = await findLinks(term, 2);
    expect(links.map((l) => l.text)).toEqual([url]);
  });

  it("does not join across a genuine short line followed by unrelated text", async () => {
    const term = new Terminal({ cols: 40, rows: 5, allowProposedApi: true });
    await write(term, "https://example.com/short\r\nhello world");

    const links = await findLinks(term, 1);
    expect(links.map((l) => l.text)).toEqual(["https://example.com/short"]);
  });
});
