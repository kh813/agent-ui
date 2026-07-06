import { useState, useEffect, useRef, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Terminal } from "@xterm/xterm";
import { useChatSession } from "./hooks/useChatSession";
import { TerminalView } from "./components/TerminalView";
import { subscribeToTauriEvent } from "./lib/tauriListener";
import { themes } from "./utils/themes";
import "./App.css";

interface AgentStatus {
  installed: boolean;
  path: string | null;
  version: string | null;
}

// Claude Code is hidden for now: a paid Claude subscription already lets users
// run Claude Code directly from Claude Desktop, so this app isn't needed for it.
// Kept behind a flag in case that changes and the entry needs to come back.
const SHOW_CLAUDE_CODE_ENTRY = false;

interface UpdateStatus {
  current_version: string | null;
  latest_version: string | null;
  update_available: boolean;
}

function App() {
  const isWindows = window.navigator.userAgent.includes("Windows");
  const defaultShell = isWindows ? "powershell.exe" : "zsh";

  const [shellPath, setShellPath] = useState(defaultShell);
  const [shellArgs, setShellArgs] = useState("");
  const [input, setInput] = useState("");

  // Theme State
  const [currentThemeId, setCurrentThemeId] = useState(() => {
    return localStorage.getItem("agent-ui-theme") || "light";
  });

  // Sync theme with body class
  useEffect(() => {
    localStorage.setItem("agent-ui-theme", currentThemeId);
    
    // Remove all theme classes first
    const classesToRemove = Array.from(document.body.classList).filter(c => c.startsWith("theme-"));
    classesToRemove.forEach(c => document.body.classList.remove(c));
    
    // Add specific theme class
    document.body.classList.add(`theme-${currentThemeId}`);
    
    // Also toggle generic theme-dark helper if needed
    const isDark = themes[currentThemeId]?.isDark ?? false;
    document.body.classList.toggle("theme-dark", isDark);
  }, [currentThemeId]);

  // Agent Onboarding & Selection States
  const [selectedAgentId, setSelectedAgentId] = useState("agy");
  const [agyStatus, setAgyStatus] = useState<AgentStatus>({
    installed: false,
    path: null,
    version: null,
  });

  // Update States
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus>({
    current_version: null,
    latest_version: null,
    update_available: false,
  });
  const [autoCheckUpdate, setAutoCheckUpdate] = useState(() => {
    const saved = localStorage.getItem("autoCheckUpdate");
    return saved !== "false"; // Default to true
  });

  const [isInstalling, setIsInstalling] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isInstallTerminalOpen, setIsInstallTerminalOpen] = useState(false);

  const terminalRef = useRef<Terminal | null>(null);
  const terminalSizeRef = useRef<{ rows: number; cols: number } | null>(null);
  const hasAutoStartedRef = useRef(false);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True once the terminal's size has stopped changing for a short while.
  // Right after mount, the fitted size can shift once or twice (fonts
  // settling, minor layout reflow), each of which is a real resize sent to
  // the PTY. If a session is auto-started before that settles, agy ends up
  // redrawing its whole startup screen for each of those changes back to
  // back, and can leave a duplicated leftover line (e.g. the bottom status
  // bar) behind - so auto-start waits for this instead of firing immediately.
  const [terminalSizeSettled, setTerminalSizeSettled] = useState(false);

  // Raw PTY output handler to write directly to xterm.js. The terminal is
  // the single source of truth for what agy has rendered - no reconstruction
  // or cleanup happens here, so it can never diverge from the real session.
  // Bytes (not a decoded string) are passed straight through so xterm.js's
  // own UTF-8 decoder handles multi-byte characters split across PTY reads.
  // Stable identity (useCallback) matters here: TerminalView's mount effect
  // and useChatSession's event-listener effect both depend on this function,
  // so a new reference on every render would tear down and remount the
  // terminal (losing scrollback) and re-subscribe PTY listeners on every
  // keystroke in the input box.
  const handleRawOutput = useCallback((raw: Uint8Array) => {
    if (terminalRef.current) {
      terminalRef.current.write(raw);
    }
  }, []);

  // Forwards keys typed directly into the terminal to the PTY.
  const handleTerminalInput = useCallback((data: string) => {
    invoke("write_to_pty", { input: data });
  }, []);

  // Keeps the PTY's reported window size in sync with what xterm.js is
  // actually rendering. A mismatch here is what let agy's cursor-relative
  // redraws (e.g. "up N rows, clear, redraw") target the wrong row and leave
  // stale content behind instead of overwriting it.
  const handleTerminalResize = useCallback((size: { rows: number; cols: number }) => {
    terminalSizeRef.current = size;
    invoke("resize_pty", size).catch(() => {
      // No active session yet - the size will be used when one starts.
    });

    setTerminalSizeSettled(false);
    if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    settleTimerRef.current = setTimeout(() => {
      settleTimerRef.current = null;
      setTerminalSizeSettled(true);
    }, 300);
  }, []);

  const getTerminalSize = useCallback(() => terminalSizeRef.current ?? undefined, []);

  const {
    cwd,
    status,
    activePrompt,
    statusMessage,
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
    getTerminalSize,
  });

  // Detect installer CLI path and version
  const checkAgentStatus = useCallback(async () => {
    try {
      const res = await invoke<AgentStatus>("detect_agent", { agentId: "agy" });
      setAgyStatus(res);

      if (res.installed && res.path) {
        setShellPath(res.path);
        setShellArgs(""); // Reset args, start agy without arguments
      }
    } catch (e) {
      console.error("Failed to detect agy status:", e);
    }
  }, []);

  // Check for updates
  const checkUpdateStatus = useCallback(async () => {
    try {
      const res = await invoke<UpdateStatus>("check_agent_update", { agentId: "agy" });
      setUpdateStatus(res);
    } catch (e) {
      console.error("Failed to check agent update:", e);
    }
  }, []);

  // Run initial check on startup
  useEffect(() => {
    checkAgentStatus();
  }, [checkAgentStatus]);

  // Check updates if installed and enabled
  useEffect(() => {
    if (agyStatus.installed && autoCheckUpdate) {
      checkUpdateStatus();
    }
  }, [agyStatus.installed, autoCheckUpdate, checkUpdateStatus]);

  // Auto-start a session as soon as Antigravity is detected as installed and
  // the terminal's size has settled - it's currently the only supported
  // agent, so there's no need to make the user click "Start Session" every
  // time they open the app.
  useEffect(() => {
    if (agyStatus.installed && status === "idle" && terminalSizeSettled && !hasAutoStartedRef.current) {
      hasAutoStartedRef.current = true;
      startSession();
    }
  }, [agyStatus.installed, status, terminalSizeSettled, startSession]);

  // Listen to PTY termination during installation and updates
  useEffect(() => {
    const unsubStatus = subscribeToTauriEvent(
      listen<string>("pty-status", (event) => {
        if (event.payload === "terminated") {
          if (isInstalling) {
            setIsInstalling(false);
            checkAgentStatus();
          }
          if (isUpdating) {
            setIsUpdating(false);
            checkAgentStatus().then(() => {
              checkUpdateStatus();
            });
          }
        }
      })
    );

    return unsubStatus;
  }, [isInstalling, isUpdating, checkAgentStatus, checkUpdateStatus]);

  // Trigger installation via PTY
  const handleInstallAgy = async () => {
    try {
      setIsInstalling(true);
      setIsInstallTerminalOpen(true); // Open console automatically to show progress logs

      const installCmd = await invoke<{ command: string; args: string[] }>("get_install_command", {
        agentId: "agy",
      });

      await invoke("start_pty", {
        command: installCmd.command,
        args: installCmd.args,
        cwd: null,
        rows: terminalSizeRef.current?.rows,
        cols: terminalSizeRef.current?.cols,
      });
    } catch (e: any) {
      setIsInstalling(false);
      console.error("Installation failed to launch:", e);
      alert(`Failed to launch installer: ${e.toString()}`);
    }
  };

  // Trigger update via PTY. This reuses the same always-visible main
  // terminal (the backend only ever runs one PTY session at a time), so no
  // separate terminal instance is needed here.
  const handleUpdateAgy = async () => {
    try {
      setIsUpdating(true);

      const updateCmd = await invoke<{ command: string; args: string[] }>("get_update_command", {
        agentId: "agy",
      });

      await invoke("start_pty", {
        command: updateCmd.command,
        args: updateCmd.args,
        cwd: null,
        rows: terminalSizeRef.current?.rows,
        cols: terminalSizeRef.current?.cols,
      });
    } catch (e: any) {
      setIsUpdating(false);
      console.error("Update failed to launch:", e);
      alert(`Failed to launch updater: ${e.toString()}`);
    }
  };

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

  const hasActivePrompt = activePrompt !== null;

  return (
    <div className="app-container">
      {/* Header and Connection Panel */}
      <header className="app-header">
        <h1 className="app-title">agent-ui Chat Console</h1>

        <div className="controls-group">
          <select
            className="theme-selector"
            value={currentThemeId}
            onChange={(e) => setCurrentThemeId(e.target.value)}
            title="Select Theme"
          >
            {Object.entries(themes).map(([id, t]) => (
              <option key={id} value={id}>
                {t.name}
              </option>
            ))}
          </select>

          {agyStatus.installed && (
            <>
              <div className="cwd-display" title={cwd || "Default working directory"}>
                <span className="cwd-label">CWD:</span>
                <span className="cwd-path">{cwd || "App Location (Default)"}</span>
              </div>

              <button
                className="secondary"
                onClick={handleSelectDirectory}
                disabled={status === "running"}
              >
                Change Dir
              </button>

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
            </>
          )}
        </div>
      </header>

      {/* Update Alert Notification Banner */}
      {updateStatus.update_available && agyStatus.installed && (
        <div className="update-banner" style={{
          background: "rgba(245, 158, 11, 0.15)",
          borderBottom: "1px solid rgba(245, 158, 11, 0.25)",
          padding: "10px 20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.85rem",
          color: "#f59e0b",
          backdropFilter: "blur(8px)"
        }}>
          <div>
            ⚠️ <strong>Antigravity CLI</strong> の新バージョン <strong>{updateStatus.latest_version}</strong> が利用可能です。(現在のバージョン: {updateStatus.current_version})
            <span style={{ fontSize: "0.75rem", color: "#94a3b8", marginLeft: "12px" }}>
              ※本エージェントは自己更新に対応しています。二重更新の防止のため、他で実行中の場合は終了をお待ちください。
            </span>
          </div>
          <button
            className="primary"
            onClick={handleUpdateAgy}
            disabled={isUpdating}
            style={{
              background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
              border: "none",
              color: "#fff",
              padding: "6px 14px",
              borderRadius: "6px",
              fontWeight: "600",
              cursor: "pointer",
              fontSize: "0.8rem"
            }}
          >
            {isUpdating ? "更新中 (ログ確認)..." : "今すぐ更新"}
          </button>
        </div>
      )}

      {/* Session status banner (former system messages: session start, skill
          rebuild progress, stop, errors). Always rendered at the same size
          (padding/border/margin never change, only color/content do) so
          it appearing or disappearing can never resize the terminal below
          it - that used to cause a real PTY resize a few seconds into a
          session, which could race with agy's own async UI updates (e.g.
          its account-quota badge) and leave the screen looking corrupted. */}
      <div style={{
        background: statusMessage ? "rgba(59, 130, 246, 0.1)" : "transparent",
        border: statusMessage ? "1px solid rgba(59, 130, 246, 0.2)" : "1px solid transparent",
        borderRadius: "8px",
        padding: "8px 16px",
        marginBottom: "12px",
        fontSize: "0.8rem",
        color: "#475569",
        whiteSpace: "pre-wrap",
        minHeight: "1.2em",
      }}>
        {statusMessage || " "}
      </div>

      {/* Main Body Layout with Sidebar and Panel */}
      <div className="app-body-layout">
        {/* Sidebar panel */}
        <aside className="sidebar">
          <div className="sidebar-title">AI Engines</div>

          <div className="agent-list">
            <div
              className={`agent-item ${selectedAgentId === "agy" ? "active" : ""}`}
              onClick={() => setSelectedAgentId("agy")}
              title="Antigravity CLI"
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

            {SHOW_CLAUDE_CODE_ENTRY && (
              <div className="agent-item disabled" title="Claude Code (Future Roadmap)">
                <div className="agent-name-row">
                  <span className="agent-name">Claude Code</span>
                  <span className="agent-badge not-installed" style={{ background: "rgba(100, 116, 139, 0.15)", color: "#94a3b8" }}>
                    Roadmap
                  </span>
                </div>
                <div className="agent-version">Not supported</div>
              </div>
            )}
          </div>

          {/* Settings Section inside Sidebar */}
          <div style={{ marginTop: "auto", borderTop: "1px solid rgba(255, 255, 255, 0.08)", paddingTop: "16px" }}>
            <div className="sidebar-title" style={{ marginBottom: "8px" }}>App Settings</div>
            <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.8rem", color: "#94a3b8", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={autoCheckUpdate}
                onChange={(e) => {
                  setAutoCheckUpdate(e.target.checked);
                  localStorage.setItem("autoCheckUpdate", e.target.checked.toString());
                }}
              />
              起動時に更新を確認する
            </label>
          </div>
        </aside>

        {/* Main Panel View (live terminal OR Onboarding installer) */}
        {!agyStatus.installed && selectedAgentId === "agy" ? (
          /* Onboarding Panel */
          <div className="onboarding-panel" style={{ display: "flex", flexDirection: isInstallTerminalOpen ? "row" : "column", gap: "24px", width: "100%" }}>
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
            {isInstallTerminalOpen && (
              <div className="terminal-panel" style={{ flex: 1, minHeight: "350px", height: "100%" }}>
                <div className="terminal-header">
                  <span>INSTALLATION LOGS (PTY STREAM)</span>
                  <span style={{ color: "#ef4444" }}>RUNNING</span>
                </div>
                <div style={{ flex: 1, minHeight: 0, minWidth: 0 }}>
                  <TerminalView
                    terminalRef={terminalRef}
                    onData={handleTerminalInput}
                    onResize={handleTerminalResize}
                    theme={themes[currentThemeId].terminal}
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Live Antigravity Terminal Session */
          <div className="main-view-layout" style={{ flex: 1 }}>
            <div className="chat-panel">
              <div className="terminal-panel" style={{ flex: 1 }}>
                <div className="terminal-header">
                  <span>{isUpdating ? "UPDATE LOGS (PTY STREAM)" : "ANTIGRAVITY CLI"}</span>
                  <span style={{ color: status === "running" ? "#4caf50" : "#94a3b8" }}>
                    {status.toUpperCase()}
                  </span>
                </div>
                <div style={{ flex: 1, minHeight: 0, minWidth: 0 }}>
                  <TerminalView
                    terminalRef={terminalRef}
                    onData={handleTerminalInput}
                    onResize={handleTerminalResize}
                    theme={themes[currentThemeId].terminal}
                  />
                </div>
              </div>

              {/* Structured, clickable UI for interactive prompts (folder
                  trust, tool permission, login link) so novice users don't
                  have to navigate agy's own arrow-key prompts by hand. */}
              {activePrompt && (
                <div style={{
                  marginTop: "12px",
                  padding: "12px",
                  background: "var(--input-bg)",
                  border: "1px solid var(--input-border)",
                  borderRadius: "8px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px"
                }}>
                  <div style={{ fontSize: "0.85rem", color: "#475569", fontWeight: "600" }}>
                    {activePrompt.message}
                  </div>

                  {activePrompt.prompt_type === "confirm" && (
                    <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                      {activePrompt.options ? (
                        activePrompt.options.map((opt: string) => (
                          <button
                            key={opt}
                            className={opt.toLowerCase().includes("no") || opt.toLowerCase().includes("exit") ? "secondary" : "primary"}
                            onClick={() => respondToPrompt(opt)}
                            style={{ padding: "6px 16px" }}
                          >
                            {opt}
                          </button>
                        ))
                      ) : (
                        <>
                          <button
                            className="primary"
                            onClick={() => respondToPrompt("y")}
                            style={{ padding: "6px 16px" }}
                          >
                            はい (Yes)
                          </button>
                          <button
                            className="secondary"
                            onClick={() => respondToPrompt("n")}
                            style={{ padding: "6px 16px" }}
                          >
                            いいえ (No)
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {activePrompt.prompt_type === "path" && (
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
                            respondToPrompt(selected);
                          }
                        }}
                        style={{ padding: "6px 16px" }}
                      >
                        フォルダを選択
                      </button>
                    </div>
                  )}

                  {activePrompt.prompt_type === "login" && activePrompt.url && (
                    <div>
                      <a
                        href={activePrompt.url}
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
                      ? "Please respond to the interactive prompt above..."
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
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
