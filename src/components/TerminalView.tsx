import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { computeFitSize } from "../lib/terminalFit";
import { TerminalTheme } from "../utils/themes";

interface TerminalViewProps {
  onData?: (data: string) => void;
  terminalRef: React.MutableRefObject<Terminal | null>;
  onResize?: (size: { rows: number; cols: number }) => void;
  theme: TerminalTheme;
}

export function TerminalView({ onData, terminalRef, onResize, theme }: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize xterm.js Terminal
    const term = new Terminal({
      cursorBlink: true,
      theme: theme,
      fontSize: 13,
      fontFamily: "Menlo, Monaco, 'Courier New', monospace",
    });

    // Open terminal in the container DOM element
    term.open(containerRef.current);

    const fitToContentBox = (widthPx: number, heightPx: number) => {
      const size = computeFitSize(term, widthPx, heightPx);
      if (size && (size.cols !== term.cols || size.rows !== term.rows)) {
        term.resize(size.cols, size.rows);
      }
    };

    // clientWidth/clientHeight are the container's own content-box size
    // (padding included, border/scrollbar excluded), independent of
    // whatever xterm renders inside it.
    const style = window.getComputedStyle(containerRef.current);
    const paddingX = parseInt(style.paddingLeft, 10) + parseInt(style.paddingRight, 10);
    const paddingY = parseInt(style.paddingTop, 10) + parseInt(style.paddingBottom, 10);
    fitToContentBox(containerRef.current.clientWidth - paddingX, containerRef.current.clientHeight - paddingY);

    terminalRef.current = term;

    let lastReportedSize = { rows: term.rows, cols: term.cols };
    onResize?.(lastReportedSize);

    // Only notify the PTY when the row/col grid actually changes - a resize
    // (SIGWINCH-equivalent) makes agy redraw its whole UI from scratch, and
    // ResizeObserver can fire many times for sub-character-cell pixel
    // changes that don't change the grid at all. Reporting those as resizes
    // triggers redundant agy redraws that can race with each other and
    // briefly leave a duplicated row (e.g. the bottom status bar) on screen.
    const reportSizeIfChanged = () => {
      if (term.rows !== lastReportedSize.rows || term.cols !== lastReportedSize.cols) {
        lastReportedSize = { rows: term.rows, cols: term.cols };
        onResize?.(lastReportedSize);
      }
    };

    // Handle user inputs directly typed inside the debug terminal
    const dataListener = term.onData((data) => {
      if (onData) {
        onData(data);
      }
    });

    // Resize observer to auto-fit terminal on container layout changes.
    // Debounced so a burst of layout events (e.g. window drag-resize, or
    // panels settling right after mount) coalesces into a single fit/resize
    // once things stop moving, instead of one PTY resize per intermediate
    // frame. Uses the ResizeObserver entry's own contentRect (the box that
    // triggered this callback) rather than re-measuring the DOM afterward,
    // so resizing the terminal can never feed back into another observed
    // size change of its own container.
    let resizeDebounceTimer: ReturnType<typeof setTimeout> | null = null;
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;

      if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer);
      resizeDebounceTimer = setTimeout(() => {
        resizeDebounceTimer = null;
        try {
          fitToContentBox(width, height);
          reportSizeIfChanged();
        } catch (e) {
          // Suppress layout errors
        }
      }, 120);
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      dataListener.dispose();
      resizeObserver.disconnect();
      if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer);
      term.dispose();
      terminalRef.current = null;
    };
  }, [onData, terminalRef, onResize]);

  // Handle dynamic theme changes without re-creating terminal instance
  useEffect(() => {
    if (terminalRef.current && theme) {
      terminalRef.current.options.theme = theme;
    }
  }, [theme, terminalRef]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: theme.background,
        padding: "5px",
        borderRadius: "5px",
        overflow: "hidden",
        transition: "background-color 0.2s ease",
      }}
    />
  );
}
