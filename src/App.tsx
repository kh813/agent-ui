import { useState, useEffect, useRef, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Terminal } from "@xterm/xterm";
import { useChatSession } from "./hooks/useChatSession";
import { TerminalView } from "./components/TerminalView";
import { Markdown } from "./components/Markdown";
import "./App.css";

interface AgentStatus {
  installed: boolean;
  path: string | null;
  version: string | null;
}

function App() {
  const isWindows = window.navigator.userAgent.includes("Windows");
  const defaultShell = isWindows ? "powershell.exe" : "zsh";

  const [shellPath, setShellPath] = useState(defaultShell);
  const [shellArgs, setShellArgs] = useState("");
  const [input, setInput] = useState("");

  // Agent Onboarding & Selection States
  const [selectedAgentId, setSelectedAgentId] = useState("agy");
  const [agyStatus, setAgyStatus] = useState<AgentStatus>({
    installed: false,
    path: null,
    version: null,
  });
  const [isInstalling, setIsInstalling] = useState(false);

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

  // Detect installer CLI path and version
  const checkAgentStatus = useCallback(async () => {
    try {
      const res = await invoke<AgentStatus>("detect_agent", { agentId: "agy" });
      setAgyStatus(res);
      
      // If installed, set the target shell path directly to the resolved agy binary!
      // This is crucial: once detected, any new chat session will run "agy" directly
      if (res.installed && res.path) {
        setShellPath(res.path);
        setShellArgs(""); // Clear shell args for agy wrapping
      }
    } catch (e) {
      console.error("Failed to detect agy status:", e);
    }
  }, []);

  // Run initial check on startup
  useEffect(() => {
    checkAgentStatus();
  }, [checkAgentStatus]);

  // Listen to PTY termination during installation
  useEffect(() => {
    let unlistenStatus: (() => void) | null = null;

    listen<string>("pty-status", (event) => {
      if (event.payload === "terminated" && isInstalling) {
        setIsInstalling(false);
        // Rescan status after installer process terminates
        checkAgentStatus();
      }
    }).then((fn) => {
      unlistenStatus = fn;
    });

    return () => {
      if (unlistenStatus) unlistenStatus();
    };
  }, [isInstalling, checkAgentStatus]);

  // Trigger installation via PTY
  const handleInstallAgy = async () => {
    try {
      setIsInstalling(true);
      setIsTerminalOpen(true); // Open console automatically to show progress logs
      
      // Get install command definition from JSON via rust backend
      const installCmd = await invoke<{ command: string; args: string[] }>("get_install_command", {
        agentId: "agy",
      });

      // Run the installer command inside portable-pty
      await invoke("start_pty", {
        command: installCmd.command,
        args: installCmd.args,
        cwd: null,
      });
    } catch (e: any) {
      setIsInstalling(false);
      console.error("Installation failed to launch:", e);
      alert(`Failed to launch installer: ${e.toString()}`);
    }
  };

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
        <h1 className="app-title">Antigravity Chat Console</h1>
        
        {agyStatus.installed && (
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
        )}
      </header>

      {/* Main Body Layout with Sidebar and Panel */}
      <div className="app-body-layout">
        {/* Sidebar panel */}
        <aside className="sidebar">
          <div className="sidebar-title">AI Engines</div>
          
          <div className="agent-list">
            {/* Antigravity engine (agy) */}
            <div 
              className={`agent-item ${selectedAgentId === "agy" ? "active" : ""}`}
              onClick={() => setSelectedAgentId("agy")}
            >
              <div className="agent-name-row">
                <span className="agent-name">Antigravity</span>
                <span className={`agent-badge ${agyStatus.installed ? "installed" : "not-installed"}`}>
                  {agyStatus.installed ? "Installed" : "Missing"}
                </span>
              </div>
              <div className="agent-version">
                {agyStatus.installed ? agyStatus.version || "version loaded" : "Require setup"}
              </div>
            </div>

            {/* Future engine: Claude Code (greyed out / placeholder) */}
            <div className="agent-item disabled" title="Claude Code (Future Roadmap)">
              <div className="agent-name-row">
                <span className="agent-name">Claude Code</span>
                <span className="agent-badge not-installed" style={{ background: "rgba(100, 116, 139, 0.15)", color: "#94a3b8" }}>
                  Roadmap
                </span>
              </div>
              <div className="agent-version">Not supported</div>
            </div>
          </div>
        </aside>

        {/* Main Panel View (Chat OR Onboarding installer) */}
        {!agyStatus.installed && selectedAgentId === "agy" ? (
          /* Onboarding Panel */
          <div className="onboarding-panel" style={{ display: "flex", flexDirection: isTerminalOpen ? "row" : "column", gap: "24px", width: "100%" }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <div className="onboarding-icon">🌌</div>
              <h2 className="onboarding-title">Antigravity CLI required</h2>
              <p className="onboarding-desc">
                This desktop client runs Antigravity CLI (agy) under the hood to perform tasks. 
                We detected that "agy" is currently not installed or not in your system path.
              </p>
              
              {isInstalling ? (
                <button className="primary" disabled style={{ background: "#64748b" }}>
                  Installing agent (logs in console)...
                </button>
              ) : (
                <button className="primary" onClick={handleInstallAgy} style={{ background: "linear-gradient(135deg, #10b981 0%, #059669 100%)", fontSize: "1.1rem", padding: "12px 24px" }}>
                  Install Antigravity CLI
                </button>
              )}
            </div>

            {/* Embedded Live Console for Installer Logs */}
            {isTerminalOpen && (
              <div className="terminal-panel" style={{ flex: 1, minHeight: "350px", height: "100%" }}>
                <div className="terminal-header">
                  <span>INSTALLATION LOGS (PTY STREAM)</span>
                  <span style={{ color: "#ef4444" }}>RUNNING</span>
                </div>
                <div style={{ flex: 1, minHeight: 0 }}>
                  <TerminalView 
                    terminalRef={terminalRef}
                    onData={(data) => {
                      // Allow input only if process is active
                      invoke("write_to_pty", { input: data });
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Normal Chat Interface */
          <div className="main-view-layout" style={{ flex: 1 }}>
            {/* Chat History Panel */}
            <div className="chat-panel">
              <div className="messages-list">
                {messages.length === 0 ? (
                  <div className="message-row system">
                    <div className="message-bubble">
                      Welcome to Antigravity. Start Session and type a query.
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
        )}
      </div>
    </div>
  );
}

export default App;
