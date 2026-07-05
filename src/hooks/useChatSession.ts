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
  const lastSentTextRef = useRef<string>("");
  const sessionOutputRef = useRef<string>("");

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
        // Task 9-5 & 9-6: Check and auto-rebuild skill folder if exists
        const hasSkill = await invoke<boolean>("check_skill_folder", { cwd: targetCwd || "" });
        if (hasSkill) {
          setMessages((prev) => [
            ...prev,
            {
              id: `sys-skill-build-${Date.now()}`,
              sender: "system",
              content: "🛠️ Skill folder detected. Rebuilding skill before starting session...",
              timestamp: Date.now(),
            },
          ]);

          try {
            const buildResult = await invoke<string>("build_skill", {
              cwd: targetCwd || "",
              agentId: "agy",
            });
            setMessages((prev) => [
              ...prev,
              {
                id: `sys-skill-ok-${Date.now()}`,
                sender: "system",
                content: `✓ Skill rebuild succeeded!\n${buildResult}`,
                timestamp: Date.now(),
              },
            ]);
          } catch (buildErr: any) {
            setMessages((prev) => [
              ...prev,
              {
                id: `sys-skill-fail-${Date.now()}`,
                sender: "system",
                content: `⚠️ Skill rebuild failed. Starting session anyway.\nError details:\n${buildErr.toString()}`,
                timestamp: Date.now(),
                status: "error",
              },
            ]);
          }
        }

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
      lastSentTextRef.current = text;
      sessionOutputRef.current = "";

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
        await invoke("write_to_pty", { input: text + "\r" });
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
      lastSentTextRef.current = responseText;

      const userMsg: Message = {
        id: `user-res-${Date.now()}`,
        sender: "user",
        content: responseText,
        timestamp: Date.now(),
      };

      sessionOutputRef.current = "";

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

      let inputToSend = responseText + "\n";
      if (responseText === "Yes, I trust this folder" || responseText === "Yes") {
        inputToSend = "\r";
      } else if (responseText === "No, exit") {
        inputToSend = "\u001b[B\r";
      } else if (responseText.includes("always allow in this conversation")) {
        inputToSend = "\u001b[B\r";
      } else if (responseText.includes("always allow (Persist to settings.json)") || responseText.includes("Persist to settings.json")) {
        inputToSend = "\u001b[B\u001b[B\r";
      } else if (responseText === "No") {
        inputToSend = "\u001b[B\u001b[B\u001b[B\r";
      }

      try {
        await invoke("write_to_pty", { input: inputToSend });
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

    let outputBuffer = "";
    let flushTimer: ReturnType<typeof setTimeout> | null = null;

    // Output receiver with 30ms throttling buffer optimization
    listen<{ data: string }>("pty-output", (event) => {
      const raw = event.payload.data;
      if (onRawOutput) {
        onRawOutput(raw);
      }

      // Accumulate raw terminal output to prevent ANSI code fragmentation across chunks
      outputBuffer += raw;

      if (!flushTimer) {
        flushTimer = setTimeout(() => {
          let rawToClean = outputBuffer;
          outputBuffer = "";
          flushTimer = null;

          // Detect incomplete ANSI escape sequences at the end of the buffered raw text (carry-over)
          const incompleteAnsiRegex = /\x1b[[()#;?]*[0-9;]*$/;
          const match = rawToClean.match(incompleteAnsiRegex);
          if (match) {
            const incompletePart = match[0];
            outputBuffer = incompletePart; // Save to next chunk buffer
            rawToClean = rawToClean.slice(0, -incompletePart.length); // Process only complete portion
          }

          // Append complete chunks to our turn cumulative buffer
          sessionOutputRef.current += rawToClean;

          let cleanText = cleanTerminalOutput(sessionOutputRef.current);
          
          // Check if agy has returned to interactive prompt input mode (? for shortcuts)
          const hasAgyPrompt = sessionOutputRef.current.includes("? for shortcuts") || sessionOutputRef.current.includes("shortcuts") || cleanText.includes("shortcuts");

          // Filter out user's last sent query echo-back and any fragmented echoing of it (substrings)
          const lastSent = lastSentTextRef.current;
          if (lastSent) {
            const normLast = lastSent.replace(/\s+/g, "").toLowerCase();
            const lines = cleanText.split("\n");
            const filteredLines = lines.filter((line) => {
              const trimmed = line.trim();
              if (!trimmed) return true;
              
              const normTrimmed = trimmed.replace(/\s+/g, "").toLowerCase();
              // Filter out echo if the normalized line is a substring of normalized last query (or vice versa)
              if (normTrimmed.length >= 5 && (normLast.includes(normTrimmed) || normTrimmed.includes(normLast))) {
                return false;
              }
              return true;
            });
            cleanText = filteredLines.join("\n");
          }

          if (!cleanText.trim() && !hasAgyPrompt) return;

          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const lastMsg = prev[prev.length - 1];

            const nextStatus = hasAgyPrompt ? ("completed" as const) : lastMsg.status;

            if (lastMsg.sender === "assistant") {
              return [
                ...prev.slice(0, -1),
                {
                  ...lastMsg,
                  content: cleanText, // REPLACE with turn cumulative clean text
                  status: nextStatus,
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
                  status: hasAgyPrompt ? ("completed" as const) : ("thinking" as const),
                },
              ];
            }
          });
        }, 30);
      }
    }).then((fn) => {
      unlistenOutput = fn;
    });

    // PTY interactive prompt detection receiver
    listen<PtyPrompt>("pty-prompt", (event) => {
      setMessages((prev) => {
        if (prev.length === 0) {
          return [
            {
              id: `assistant-prompt-${Date.now()}`,
              sender: "assistant",
              content: "",
              timestamp: Date.now(),
              status: "completed",
              prompt: event.payload,
            },
          ];
        }
        
        const lastMsg = prev[prev.length - 1];
        if (lastMsg.sender === "assistant") {
          return [
            ...prev.slice(0, -1),
            {
              ...lastMsg,
              prompt: event.payload,
              status: "completed",
            },
          ];
        } else {
          return [
            ...prev,
            {
              id: `assistant-prompt-${Date.now()}`,
              sender: "assistant",
              content: "",
              timestamp: Date.now(),
              status: "completed",
              prompt: event.payload,
            },
          ];
        }
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
      if (flushTimer) clearTimeout(flushTimer);
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
