import { useState, useEffect, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { cleanTerminalOutput } from "../utils/ansi";

export interface PtyPrompt {
  prompt_type: "confirm" | "path" | "login";
  message: string;
  options?: string[];
  url?: string;
}

export interface Message {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  status?: "thinking" | "completed" | "error";
  prompt?: PtyPrompt;
}

export interface UseChatSessionOptions {
  command: string;
  defaultArgs?: string[];
  initialCwd?: string;
  onRawOutput?: (raw: string) => void;
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

  // Start PTY Session
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

  // Respond to an interactive PTY prompt (button clicks or path selection)
  const respondToPrompt = useCallback(
    async (messageId: string, responseText: string) => {
      if (statusRef.current !== "running") return;

      const userMsg: Message = {
        id: `user-res-${Date.now()}`,
        sender: "user",
        content: responseText,
        timestamp: Date.now(),
      };

      // Resolve the active prompt by removing it from the target message and starting a new thinking block
      setMessages((prev) => {
        const updatedMessages = prev.map((msg) => {
          if (msg.id === messageId) {
            // Remove prompt field to hide the UI buttons after selection
            const { prompt, ...rest } = msg;
            return {
              ...rest,
              status: "completed" as const,
            };
          }
          return msg;
        });

        const nextAssistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          sender: "assistant",
          content: "",
          timestamp: Date.now() + 1,
          status: "thinking",
        };

        return [...updatedMessages, userMsg, nextAssistantMsg];
      });

      try {
        await invoke("write_to_pty", { input: responseText + "\n" });
      } catch (e: any) {
        console.error("Failed to write response to PTY:", e);
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

  // Listen to PTY outputs, status changes, and prompt detections
  useEffect(() => {
    let unlistenOutput: (() => void) | null = null;
    let unlistenStatus: (() => void) | null = null;
    let unlistenPrompt: (() => void) | null = null;

    // Output receiver
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

        if (lastMsg.sender === "assistant" && lastMsg.status === "thinking") {
          return [
            ...prev.slice(0, -1),
            {
              ...lastMsg,
              content: lastMsg.content + cleanText,
            },
          ];
        } else {
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

    // PTY interactive prompt detection receiver
    listen<PtyPrompt>("pty-prompt", (event) => {
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const lastMsg = prev[prev.length - 1];
        
        // Attach prompt metadata to the active assistant message
        if (lastMsg.sender === "assistant") {
          return [
            ...prev.slice(0, -1),
            {
              ...lastMsg,
              prompt: event.payload,
              status: "completed", // Stop loading/thinking animation when prompt awaits action
            },
          ];
        }
        return prev;
      });
    }).then((fn) => {
      unlistenPrompt = fn;
    });

    // PTY status receiver
    listen<string>("pty-status", (event) => {
      if (event.payload === "terminated") {
        setStatus("idle");
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
      if (unlistenPrompt) unlistenPrompt();
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
    respondToPrompt,
    changeCwd,
    setMessages,
  };
}
