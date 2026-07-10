import { useState, useEffect, useRef, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Terminal } from "@xterm/xterm";
import { useChatSession } from "./hooks/useChatSession";
import { TerminalView } from "./components/TerminalView";
import { subscribeToTauriEvent } from "./lib/tauriListener";
import { themes } from "./utils/themes";
import { Lang, translations } from "./utils/i18n";
import "./App.css";

interface AgentStatus {
  installed: boolean;
  path: string | null;
  version: string | null;
}

interface EngineConfig {
  id: string;
  name: string;
  command: string;
  args: string[];
}

interface AppConfig {
  app_name: string;
  default_theme: string;
  font_family: string;
  font_size: number;
  engines: EngineConfig[];
}


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

    // Keep the native app menu's Theme checkmarks in sync
    invoke("set_theme", { themeId: currentThemeId }).catch(() => {});
  }, [currentThemeId]);

  // Apply theme changes made from the native app menu
  useEffect(() => {
    const unsub = subscribeToTauriEvent(
      listen<string>("theme-changed", (event) => {
        setCurrentThemeId(event.payload);
      })
    );

    return unsub;
  }, []);

  // OS locale auto detection (JA if OS language starts with 'ja', otherwise EN)
  const lang: Lang = navigator.language.startsWith("ja") ? "ja" : "en";

  // Translation helper
  const t = (key: keyof typeof translations['ja']) => {
    return translations[lang][key];
  };

  // Config & Selection States
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [selectedAgentId, setSelectedAgentId] = useState("agy");

  const currentAgentStatus = agentStatuses[selectedAgentId] || {
    installed: false,
    path: null,
    version: null,
  };

  // Derived from selectedAgentId so this naturally becomes "the active
  // tab's engine" once multiple concurrent sessions/tabs are supported.
  const selectedEngine = appConfig?.engines.find((e) => e.id === selectedAgentId);

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

  // Keep the native app menu's "Check for Updates on Startup" checkmark in sync
  useEffect(() => {
    localStorage.setItem("autoCheckUpdate", autoCheckUpdate.toString());
    invoke("set_auto_check_update", { enabled: autoCheckUpdate }).catch(() => {});
  }, [autoCheckUpdate]);

  // Apply changes made from the native app menu
  useEffect(() => {
    const unsub = subscribeToTauriEvent(
      listen<boolean>("auto-check-update-changed", (event) => {
        setAutoCheckUpdate(event.payload);
      })
    );

    return unsub;
  }, []);

  const [isInstalling, setIsInstalling] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isInstallTerminalOpen, setIsInstallTerminalOpen] = useState(false);

  const terminalRef = useRef<Terminal | null>(null);
  const terminalSizeRef = useRef<{ rows: number; cols: number } | null>(null);
  const hasAutoStartedRef = useRef(false);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True once the terminal's size has stopped changing for a short while.
  const [terminalSizeSettled, setTerminalSizeSettled] = useState(false);

  // Raw PTY output handler to write directly to xterm.js.
  const handleRawOutput = useCallback((raw: Uint8Array) => {
    if (terminalRef.current) {
      terminalRef.current.write(raw);
    }
  }, []);

  // Forwards keys typed directly into the terminal to the PTY.
  const handleTerminalInput = useCallback((data: string) => {
    invoke("write_to_pty", { input: data });
  }, []);

  // Keeps the PTY's reported window size in sync with what xterm.js is actually rendering.
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

  // Detect installer CLI path and version for all configured engines
  const checkAgentStatus = useCallback(async () => {
    if (!appConfig) return;
    try {
      const newStatuses: Record<string, AgentStatus> = {};
      for (const engine of appConfig.engines) {
        try {
          const status = await invoke<AgentStatus>("detect_agent", { agentId: engine.id });
          newStatuses[engine.id] = status;
        } catch (e) {
          console.error(`Failed to detect agent ${engine.id}:`, e);
          newStatuses[engine.id] = { installed: false, path: null, version: null };
        }
      }
      setAgentStatuses(newStatuses);
    } catch (e) {
      console.error("Failed to detect agent status:", e);
    }
  }, [appConfig]);

  // Check for updates
  const checkUpdateStatus = useCallback(async () => {
    try {
      const res = await invoke<UpdateStatus>("check_agent_update", { agentId: selectedAgentId });
      setUpdateStatus(res);
    } catch (e) {
      console.error("Failed to check agent update:", e);
    }
  }, [selectedAgentId]);

  // 1. Load dynamic configuration
  useEffect(() => {
    const loadAppConfig = async () => {
      try {
        const cfg = await invoke<AppConfig>("get_app_config", { cwd: cwd || null });
        setAppConfig(cfg);
        
        const savedTheme = localStorage.getItem("agent-ui-theme");
        if (!savedTheme && cfg.default_theme) {
          setCurrentThemeId(cfg.default_theme);
        }
      } catch (e) {
        console.error("Failed to load app config:", e);
      }
    };
    loadAppConfig();
  }, [cwd]);

  // 2. Trigger status detection when configuration loads or refreshes
  useEffect(() => {
    if (!appConfig) return;
    checkAgentStatus();

    // Default select first engine if selection is missing from config
    if (appConfig.engines.length > 0) {
      const exists = appConfig.engines.some(e => e.id === selectedAgentId);
      if (!exists) {
        setSelectedAgentId(appConfig.engines[0].id);
      }
    }
  }, [appConfig, checkAgentStatus]);

  // 3. Update PTY command configuration when selection or statuses change
  useEffect(() => {
    if (!appConfig) return;
    const engine = appConfig.engines.find(e => e.id === selectedAgentId);
    const status = agentStatuses[selectedAgentId];
    if (engine && status && status.installed && status.path) {
      setShellPath(status.path);
      const args = engine.args || [];
      setShellArgs(args.join(" "));
    }
  }, [selectedAgentId, agentStatuses, appConfig]);

  // Check updates if installed and enabled
  useEffect(() => {
    if (currentAgentStatus.installed && autoCheckUpdate) {
      checkUpdateStatus();
    }
  }, [currentAgentStatus.installed, autoCheckUpdate, checkUpdateStatus]);

  // Auto-start a session as soon as the selected agent is detected as installed and terminal size settled
  useEffect(() => {
    if (currentAgentStatus.installed && status === "idle" && terminalSizeSettled && !hasAutoStartedRef.current) {
      hasAutoStartedRef.current = true;
      startSession();
    }
  }, [currentAgentStatus.installed, status, terminalSizeSettled, startSession]);

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
      alert(`${t("failedToInstall")}: ${e.toString()}`);
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
      alert(`${t("failedToUpdate")}: ${e.toString()}`);
    }
  };

  // Open directory selection dialog using Tauri Dialog API
  const handleSelectDirectory = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        defaultPath: cwd || undefined,
        title: t("selectWorkingDir"),
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
        <h1 className="app-title">{appConfig ? appConfig.app_name : t("appTitle")}</h1>

        <div className="controls-group">
          {currentAgentStatus.installed && (
            <>
              <div className="cwd-display agent-type-display" title={selectedEngine?.name}>
                <span className="cwd-label">{t("agentLabel")}:</span>
                <span className="cwd-path">{selectedEngine?.name}</span>
              </div>

              <div className="cwd-display" title={cwd || "Default working directory"}>
                <span className="cwd-label">CWD:</span>
                <span className="cwd-path">{cwd || t("appLocationDefault")}</span>
              </div>

              <button
                className="secondary"
                onClick={handleSelectDirectory}
                disabled={status === "running"}
              >
                {t("changeDir")}
              </button>

              <div className={`status-badge ${status}`}>
                {status}
              </div>

              {status === "running" ? (
                <button className="danger" onClick={stopSession}>
                  {t("stop")}
                </button>
              ) : (
                <button className="primary" onClick={handleStartPty}>
                  {t("startSession")}
                </button>
              )}
            </>
          )}
        </div>
      </header>

      {/* Update Alert Notification Banner */}
      {updateStatus.update_available && currentAgentStatus.installed && (
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
            {t("updateAvailableMsg").replace("{latest}", updateStatus.latest_version || "").replace("{current}", updateStatus.current_version || "")}
            <span style={{ fontSize: "0.75rem", color: "#94a3b8", marginLeft: "12px" }}>
              {t("updateNote")}
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
            {isUpdating ? t("updating") : t("updateNow")}
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

      {/* Main Body Layout (sidebar removed - agent info lives in the header now,
          and "check updates on startup" moved to the native app menu, so the
          main panel can use the full width) */}
      <div className="app-body-layout">
        {/* Main Panel View (live terminal OR Onboarding installer) */}
        {!currentAgentStatus.installed ? (
          /* Onboarding Panel */
          <div className="onboarding-panel" style={{ display: "flex", flexDirection: isInstallTerminalOpen ? "row" : "column", gap: "24px", width: "100%" }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <div className="onboarding-icon">🌌</div>
              <h2 className="onboarding-title">{t("installAgyRequired")}</h2>
              <p className="onboarding-desc">
                {t("installAgyDesc")}
              </p>

              {isInstalling ? (
                <button className="primary" disabled style={{ background: "#64748b" }}>
                  {t("installingAgent")}
                </button>
              ) : (
                <button className="primary" onClick={handleInstallAgy} style={{ background: "linear-gradient(135deg, #10b981 0%, #059669 100%)", fontSize: "1.1rem", padding: "12px 24px" }}>
                  {t("installButton")}
                </button>
              )}
            </div>

            {/* Embedded Live Console for Installer Logs */}
            {isInstallTerminalOpen && (
              <div className="terminal-panel" style={{ flex: 1, minHeight: "350px", height: "100%" }}>
                <div className="terminal-header">
                  <span>{t("installLogs")}</span>
                  <span style={{ color: "#ef4444" }}>{t("running").toUpperCase()}</span>
                </div>
                <div style={{ flex: 1, minHeight: 0, minWidth: 0 }}>
                  <TerminalView
                    terminalRef={terminalRef}
                    onData={handleTerminalInput}
                    onResize={handleTerminalResize}
                    theme={themes[currentThemeId].terminal}
                    fontFamily={appConfig?.font_family}
                    fontSize={appConfig?.font_size}
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
                  <span>{isUpdating ? t("updateLogs") : "ANTIGRAVITY CLI"}</span>
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
                    fontFamily={appConfig?.font_family}
                    fontSize={appConfig?.font_size}
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
                            {t("yes")}
                          </button>
                          <button
                            className="secondary"
                            onClick={() => respondToPrompt("n")}
                            style={{ padding: "6px 16px" }}
                          >
                            {t("no")}
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
                            title: t("selectPromptPath"),
                          });
                          if (selected && typeof selected === "string") {
                            respondToPrompt(selected);
                          }
                        }}
                        style={{ padding: "6px 16px" }}
                      >
                        {t("selectFolder")}
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
                        {t("openLoginBrowser")}
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
                      ? t("placeholderStartSession")
                      : hasActivePrompt
                      ? t("placeholderRespondPrompt")
                      : t("placeholderSendInput")
                  }
                  disabled={status !== "running" || hasActivePrompt}
                />
                <button
                  type="submit"
                  className="primary"
                  disabled={status !== "running" || !input.trim()}
                >
                  {t("send")}
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
