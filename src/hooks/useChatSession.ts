import { useState, useEffect, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { cleanTerminalOutput } from "../utils/ansi";

export interface Message {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  status?: "thinking" | "completed" | "error";
}

export interface UseChatSessionOptions {
  command: string;
  defaultArgs?: string[];
  initialCwd?: string;
  onRawOutput?: (raw: string) => void; // For xterm.js direct binding
}

export function useChatSession({
  command,
  defaultArgs = [],
  initialCwd = "",
  onRawOutput,
}: UseChatSessionOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [cwd, setCwd] = useState(initialCwd);
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);

  // Use refs to access current state inside event listeners
  const statusRef = useRef(status);
  const messagesRef = useRef(messages);
  const cwdRef = useRef(cwd);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    cwdRef.current = cwd;
  }, [cwd]);

  // PTY Session Control: Start PTY
  const startSession = useCallback(
    async (targetCwd: string = cwdRef.current) => {
      setStatus("idle");
      setMessages([
        {
          id: "sys-start",
          sender: "system",
          content: `Starting session in directory: ${targetCwd || "default"}`,
          timestamp: Date.now(),
        },
      ]);

      try {
        await invoke("start_pty", {
          command,
          args: defaultArgs,
          cwd: targetCwd || null,
        });
        setStatus("running");
        setCwd(targetCwd);
      } catch (e: any) {
        setStatus("error");
        setMessages((prev) => [
          ...prev,
          {
            id: `sys-err-${Date.now()}`,
            sender: "system",
            content: `Failed to start session: ${e.toString()}`,
            timestamp: Date.now(),
            status: "error",
          },
        ]);
      }
    },
    [command, defaultArgs]
  );

  // Stop PTY Session
  const stopSession = useCallback(async () => {
    try {
      await invoke("stop_pty");
      setStatus("idle");
      setMessages((prev) => [
        ...prev,
        {
          id: `sys-stop-${Date.now()}`,
          sender: "system",
          content: "Session stopped by user.",
          timestamp: Date.now(),
        },
      ]);
    } catch (e: any) {
      console.error("Failed to stop PTY:", e);
    }
  }, []);

  // Send input query to PTY
  const sendMessage = useCallback(
    async (text: string) => {
      if (statusRef.current !== "running") return;

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        sender: "user",
        content: text,
        timestamp: Date.now(),
      };

      const assistantMsg: Message = {
        id: `assistant-${Date.now()}`,
        sender: "assistant",
        content: "",
        timestamp: Date.now() + 1,
        status: "thinking",
      };

      // Add user message and prepare an empty assistant bubble
      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      try {
        await invoke("write_to_pty", { input: text + "\n" });
      } catch (e: any) {
        setMessages((prev) => [
          ...prev.slice(0, -1),
          {
            ...assistantMsg,
            content: `Error sending query: ${e.toString()}`,
            status: "error",
          },
        ]);
      }
    },
    []
  );

  // Change working directory and restart PTY
  const changeCwd = useCallback(
    async (newCwd: string) => {
      setCwd(newCwd);
      await startSession(newCwd);
    },
    [startSession]
  );

  // Listen to PTY outputs
  useEffect(() => {
    let unlistenOutput: (() => void) | null = null;
    let unlistenStatus: (() => void) | null = null;

    listen<{ data: string }>("pty-output", (event) => {
      const raw = event.payload.data;
      if (onRawOutput) {
        onRawOutput(raw);
      }

      const cleanText = cleanTerminalOutput(raw);
      if (!cleanText) return;

      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const lastMsg = prev[prev.length - 1];

        // Append to the last assistant message if it is still "thinking"
        if (lastMsg.sender === "assistant" && lastMsg.status === "thinking") {
          return [
            ...prev.slice(0, -1),
            {
              ...lastMsg,
              content: lastMsg.content + cleanText,
            },
          ];
        } else {
          // If no assistant message is active, create a new one
          return [
            ...prev,
            {
              id: `assistant-stream-${Date.now()}`,
              sender: "assistant",
              content: cleanText,
              timestamp: Date.now(),
              status: "thinking",
            },
          ];
        }
      });
    }).then((fn) => {
      unlistenOutput = fn;
    });

    listen<string>("pty-status", (event) => {
      if (event.payload === "terminated") {
        setStatus("idle");
        // Mark the active assistant message as completed
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const lastMsg = prev[prev.length - 1];
          if (lastMsg.sender === "assistant" && lastMsg.status === "thinking") {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                status: "completed",
              },
            ];
          }
          return prev;
        });
      }
    }).then((fn) => {
      unlistenStatus = fn;
    });

    return () => {
      if (unlistenOutput) unlistenOutput();
      if (unlistenStatus) unlistenStatus();
    };
  }, [onRawOutput]);

  return {
    messages,
    cwd,
    status,
    isTerminalOpen,
    setIsTerminalOpen,
    startSession,
    stopSession,
    sendMessage,
    changeCwd,
    setMessages,
  };
}
