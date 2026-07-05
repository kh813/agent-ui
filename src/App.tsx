import { useState, useEffect, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { Terminal } from "@xterm/xterm";
import { useChatSession } from "./hooks/useChatSession";
import { TerminalView } from "./components/TerminalView";
import { Markdown } from "./components/Markdown";
import "./App.css";

function App() {
  const isWindows = window.navigator.userAgent.includes("Windows");
  const defaultShell = isWindows ? "powershell.exe" : "zsh";

  const [shellPath, setShellPath] = useState(defaultShell);
  const [shellArgs, setShellArgs] = useState("");
  const [input, setInput] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);

  // Raw PTY output handler to write directly to xterm.js
  const handleRawOutput = (raw: string) => {
    if (terminalRef.current) {
      terminalRef.current.write(raw);
    }
  };

  const {
    messages,
    cwd,
    status,
    isTerminalOpen,
    setIsTerminalOpen,
    startSession,
    stopSession,
    sendMessage,
    respondToPrompt,
    changeCwd,
  } = useChatSession({
    command: shellPath,
    defaultArgs: shellArgs.trim() ? shellArgs.split(" ") : [],
    initialCwd: "",
    onRawOutput: handleRawOutput,
  });

  const hasActivePrompt = messages.some((msg) => msg.prompt !== undefined);

  // Auto-scroll chat to the bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Open directory selection dialog using Tauri Dialog API
  const handleSelectDirectory = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        defaultPath: cwd || undefined,
        title: "Select Working Directory",
      });

      if (selected && typeof selected === "string") {
        changeCwd(selected);
      }
    } catch (e) {
      console.error("Failed to open directory dialog:", e);
    }
  };

  const handleStartPty = () => {
    startSession();
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || status !== "running") return;
    sendMessage(input);
    setInput("");
  };

  return (
    <div className="app-container">
      {/* Header and Connection Panel */}
      <header className="app-header">
        <h1 className="app-title">ChatUI Debug Console</h1>
        
        <div className="controls-group">
          {/* Working directory control */}
          <div className="cwd-display" title={cwd || "Default working directory"}>
            <span className="cwd-label">CWD:</span>
            <span className="cwd-path">{cwd || "User Home (Default)"}</span>
          </div>
          
          <button 
            className="secondary" 
            onClick={handleSelectDirectory}
            disabled={status === "running"}
          >
            Change Dir
          </button>

          {/* Status indicators and Action buttons */}
          <div className={`status-badge ${status}`}>
            {status}
          </div>

          {status === "running" ? (
            <button className="danger" onClick={stopSession}>
              Stop
            </button>
          ) : (
            <button className="primary" onClick={handleStartPty}>
              Start Session
            </button>
          )}

          {/* Toggle terminal panel */}
          <button 
            className="secondary" 
            onClick={() => setIsTerminalOpen(!isTerminalOpen)}
          >
            {isTerminalOpen ? "Hide Console" : "Show Console"}
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="main-view-layout">
        {/* Chat History Panel */}
        <div className="chat-panel">
          <div className="messages-list">
            {messages.length === 0 ? (
              <div className="message-row system">
                <div className="message-bubble">
                  Press "Start Session" to initiate the interactive shell.
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div key={msg.id} className={`message-row ${msg.sender}`}>
                  <div className="message-bubble">
                    {msg.sender === "system" ? (
                      <div className="message-content">{msg.content}</div>
                    ) : (
                      <>
                        <Markdown content={msg.content} />
                        {msg.status === "thinking" && (
                          <div style={{ marginTop: "4px" }}>
                            <span className="thinking-dot"></span>
                            <span className="thinking-dot"></span>
                            <span className="thinking-dot"></span>
                          </div>
                        )}
                        {msg.prompt && (
                          <div style={{
                            marginTop: "12px",
                            padding: "12px",
                            background: "rgba(255, 255, 255, 0.05)",
                            border: "1px solid rgba(255, 255, 255, 0.1)",
                            borderRadius: "8px",
                            display: "flex",
                            flexDirection: "column",
                            gap: "8px"
                          }}>
                            <div style={{ fontSize: "0.85rem", color: "#94a3b8", fontWeight: "600" }}>
                              {msg.prompt.message}
                            </div>
                            
                            {msg.prompt.prompt_type === "confirm" && (
                              <div style={{ display: "flex", gap: "8px" }}>
                                <button 
                                  className="primary" 
                                  onClick={() => respondToPrompt(msg.id, "y")}
                                  style={{ padding: "6px 16px" }}
                                >
                                  はい (Yes)
                                </button>
                                <button 
                                  className="secondary" 
                                  onClick={() => respondToPrompt(msg.id, "n")}
                                  style={{ padding: "6px 16px" }}
                                >
                                  いいえ (No)
                                </button>
                              </div>
                            )}
                            
                            {msg.prompt.prompt_type === "path" && (
                              <div>
                                <button 
                                  className="primary" 
                                  onClick={async () => {
                                    const selected = await open({
                                      directory: true,
                                      multiple: false,
                                      title: "Select Path for CLI Prompt",
                                    });
                                    if (selected && typeof selected === "string") {
                                      respondToPrompt(msg.id, selected);
                                    }
                                  }}
                                  style={{ padding: "6px 16px" }}
                                >
                                  フォルダを選択
                                </button>
                              </div>
                            )}

                            {msg.prompt.prompt_type === "login" && msg.prompt.url && (
                              <div>
                                <a 
                                  href={msg.prompt.url} 
                                  target="_blank" 
                                  rel="noreferrer"
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    padding: "8px 16px",
                                    background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                                    color: "#fff",
                                    textDecoration: "none",
                                    borderRadius: "8px",
                                    fontWeight: "600",
                                    fontSize: "0.9rem",
                                    boxShadow: "0 2px 8px rgba(16, 185, 129, 0.4)"
                                  }}
                                >
                                  ブラウザでログインを開く
                                </a>
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Form Input Bar */}
          <form onSubmit={handleSend} className="input-form">
            <input
              className="input-field"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                status !== "running" 
                  ? "Start a session to interact" 
                  : hasActivePrompt
                  ? "Please respond to the interactive prompt below..."
                  : "Send terminal input..."
              }
              disabled={status !== "running" || hasActivePrompt}
            />
            <button 
              type="submit" 
              className="primary" 
              disabled={status !== "running" || !input.trim()}
            >
              Send
            </button>
          </form>
        </div>

        {/* Debug Terminal Panel (xterm.js) */}
        {isTerminalOpen && (
          <div className="terminal-panel">
            <div className="terminal-header">
              <span>LIVE INTERACTIVE SHELL LOG (DEBUG)</span>
              <span style={{ color: "#4caf50" }}>ONLINE</span>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <TerminalView 
                terminalRef={terminalRef}
                onData={(data) => {
                  if (status === "running") {
                    invoke("write_to_pty", { input: data });
                  }
                }}
              />
            </div>
          </div>
        )}
      </div>
      
      {/* Hidden configurations for command startup path (visible when idle) */}
      {status !== "running" && (
        <div style={{
          marginTop: "12px",
          padding: "12px",
          background: "rgba(30, 41, 59, 0.2)",
          borderRadius: "8px",
          display: "flex",
          gap: "16px",
          fontSize: "0.85rem",
          border: "1px solid rgba(255, 255, 255, 0.03)"
        }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            Shell Binary:
            <input 
              style={{ padding: "4px 8px", background: "#1e293b", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }} 
              value={shellPath} 
              onChange={(e) => setShellPath(e.target.value)} 
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            Args:
            <input 
              style={{ padding: "4px 8px", background: "#1e293b", border: "1px solid #475569", borderRadius: "4px", color: "#fff" }} 
              value={shellArgs} 
              placeholder="e.g. -l" 
              onChange={(e) => setShellArgs(e.target.value)} 
            />
          </label>
        </div>
      )}
    </div>
  );
}

export default App;
