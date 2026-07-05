import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

interface TerminalViewProps {
  onData?: (data: string) => void;
  terminalRef: React.MutableRefObject<Terminal | null>;
}

export function TerminalView({ onData, terminalRef }: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize xterm.js Terminal
    const term = new Terminal({
      cursorBlink: true,
      theme: {
        background: "#1e1e1e",
        foreground: "#ffffff",
      },
      fontSize: 13,
      fontFamily: "Menlo, Monaco, 'Courier New', monospace",
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    // Open terminal in the container DOM element
    term.open(containerRef.current);
    fitAddon.fit();

    terminalRef.current = term;

    // Handle user inputs directly typed inside the debug terminal
    const dataListener = term.onData((data) => {
      if (onData) {
        onData(data);
      }
    });

    // Resize observer to auto-fit terminal on container layout changes
    const resizeObserver = new ResizeObserver(() => {
      try {
        fitAddon.fit();
      } catch (e) {
        // Suppress layout errors
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      dataListener.dispose();
      resizeObserver.disconnect();
      term.dispose();
      terminalRef.current = null;
    };
  }, [onData, terminalRef]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: "#1e1e1e",
        padding: "5px",
        borderRadius: "5px",
        overflow: "hidden",
      }}
    />
  );
}
