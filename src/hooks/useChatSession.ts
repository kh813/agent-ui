import { useState, useEffect, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { resolvePromptResponseInput } from "../lib/promptResponse";
import { subscribeToTauriEvent } from "../lib/tauriListener";

export interface PtyPrompt {
  prompt_type: "confirm" | "path" | "login";
  message: string;
  options?: string[];
  url?: string;
}

export interface UseChatSessionOptions {
  command: string;
  defaultArgs?: string[];
  initialCwd?: string;
  onRawOutput?: (raw: Uint8Array) => void;
  // Reports the terminal's actual fitted size so the PTY can be spawned at
  // the right size from the start, rather than a guessed default that agy's
  // cursor-relative redraws could then target incorrectly.
  getTerminalSize?: () => { rows: number; cols: number } | undefined;
}

export function useChatSession({
  command,
  defaultArgs = [],
  initialCwd = "",
  onRawOutput,
  getTerminalSize,
}: UseChatSessionOptions) {
  const [cwd, setCwd] = useState(initialCwd);
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");
  const [activePrompt, setActivePrompt] = useState<PtyPrompt | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const statusRef = useRef(status);
  const cwdRef = useRef(cwd);
  const statusMessageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    cwdRef.current = cwd;
  }, [cwd]);

  const showStatusMessage = useCallback((text: string, autoClear = true) => {
    if (statusMessageTimerRef.current) {
      clearTimeout(statusMessageTimerRef.current);
      statusMessageTimerRef.current = null;
    }
    setStatusMessage(text);
    if (autoClear) {
      statusMessageTimerRef.current = setTimeout(() => setStatusMessage(null), 4000);
    }
  }, []);

  // Start PTY Session
  const startSession = useCallback(
    async (targetCwd: string = cwdRef.current) => {
      setStatus("idle");
      setActivePrompt(null);
      showStatusMessage(`Starting session in directory: ${targetCwd || "default"}`);

      try {
        // Task 9-5 & 9-6: Check and auto-rebuild skill folder if exists
        const hasSkill = await invoke<boolean>("check_skill_folder", { cwd: targetCwd || "" });
        if (hasSkill) {
          showStatusMessage("🛠️ Skill folder detected. Rebuilding skill before starting session...", false);

          try {
            await invoke<string>("build_skill", {
              cwd: targetCwd || "",
              agentId: "agy",
            });
            showStatusMessage("✓ Skill rebuild succeeded!");
          } catch (buildErr: any) {
            showStatusMessage(`⚠️ Skill rebuild failed. Starting session anyway.\n${buildErr.toString()}`, false);
          }
        }

        const size = getTerminalSize?.();
        await invoke("start_pty", {
          command,
          args: defaultArgs,
          cwd: targetCwd || null,
          rows: size?.rows,
          cols: size?.cols,
        });
        setStatus("running");
        setCwd(targetCwd);
      } catch (e: any) {
        setStatus("error");
        showStatusMessage(`Failed to start session: ${e.toString()}`, false);
      }
    },
    [command, defaultArgs, showStatusMessage, getTerminalSize]
  );

  // Stop PTY Session
  const stopSession = useCallback(async () => {
    try {
      await invoke("stop_pty");
      setStatus("idle");
      showStatusMessage("Session stopped by user.");
    } catch (e: any) {
      console.error("Failed to stop PTY:", e);
    }
  }, [showStatusMessage]);

  // Send input query to PTY
  const sendMessage = useCallback(async (text: string) => {
    if (statusRef.current !== "running") return;
    try {
      await invoke("write_to_pty", { input: text + "\r" });
    } catch (e: any) {
      console.error("Failed to send message to PTY:", e);
    }
  }, []);

  // Respond to an interactive PTY prompt (button clicks or path selection)
  const respondToPrompt = useCallback(async (responseText: string) => {
    if (statusRef.current !== "running") return;

    // Optimistically clear right away so the panel disappears the moment the
    // user clicks, instead of waiting for the next PTY redraw.
    setActivePrompt(null);

    const inputToSend = resolvePromptResponseInput(responseText);

    try {
      await invoke("write_to_pty", { input: inputToSend });
    } catch (e: any) {
      console.error("Failed to write response to PTY:", e);
    }
  }, []);

  // Change working directory and restart PTY
  const changeCwd = useCallback(
    async (newCwd: string) => {
      setCwd(newCwd);
      await startSession(newCwd);
    },
    [startSession]
  );

  // Listen to PTY outputs, status changes, and prompt detections
  useEffect(() => {
    // Raw bytes (not a decoded string - see PtyOutputPayload in pty.rs) go
    // straight to the terminal view. It's a real terminal emulator with its
    // own UTF-8 decoder that correctly buffers a multi-byte character split
    // across separate write() calls, so it resolves cursor movement,
    // redraws, and chunk-boundary encoding all on its own.
    const unsubOutput = subscribeToTauriEvent(
      listen<{ data: number[] }>("pty-output", (event) => {
        onRawOutput?.(new Uint8Array(event.payload.data));
      })
    );

    // PTY interactive prompt detection receiver
    const unsubPrompt = subscribeToTauriEvent(
      listen<PtyPrompt>("pty-prompt", (event) => {
        setActivePrompt(event.payload);
      })
    );

    // PTY status receiver
    const unsubStatus = subscribeToTauriEvent(
      listen<string>("pty-status", (event) => {
        if (event.payload === "terminated") {
          setStatus("idle");
        }
      })
    );

    return () => {
      unsubOutput();
      unsubStatus();
      unsubPrompt();
    };
  }, [onRawOutput]);

  return {
    cwd,
    status,
    activePrompt,
    statusMessage,
    startSession,
    stopSession,
    sendMessage,
    respondToPrompt,
    changeCwd,
  };
}
