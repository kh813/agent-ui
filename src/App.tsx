import { useState, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import "./App.css";

interface PtyOutputPayload {
  data: string;
}

function App() {
  // PTY関連ステート
  const [command, setCommand] = useState(
    window.navigator.userAgent.includes("Windows") ? "cmd.exe" : "sh"
  );
  const [args, setArgs] = useState("");
  const [cwd, setCwd] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [status, setStatus] = useState("stopped");

  const outputRef = useRef<HTMLPreElement>(null);

  // PTYの出力イベントリスナー設定
  useEffect(() => {
    let unlistenOutput: (() => void) | null = null;
    let unlistenStatus: (() => void) | null = null;

    // 出力リスナー
    listen<PtyOutputPayload>("pty-output", (event) => {
      setOutput((prev) => prev + event.payload.data);
    }).then((fn) => {
      unlistenOutput = fn;
    });

    // ステータスリスナー
    listen<string>("pty-status", (event) => {
      setStatus(event.payload);
    }).then((fn) => {
      unlistenStatus = fn;
    });

    return () => {
      if (unlistenOutput) unlistenOutput();
      if (unlistenStatus) unlistenStatus();
    };
  }, []);

  // 出力があるたびに最下部へスクロール
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output]);

  // PTYの開始
  const handleStart = async () => {
    setOutput("");
    setStatus("starting");
    const parsedArgs = args.trim() ? args.split(" ") : [];
    try {
      await invoke("start_pty", { command, args: parsedArgs, cwd });
      setStatus("running");
    } catch (e: any) {
      setOutput((prev) => prev + `\n[Error starting PTY: ${e.toString()}]\n`);
      setStatus("stopped");
    }
  };

  // PTYへの送信
  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input) return;

    try {
      // 改行を含めて書き込む
      await invoke("write_to_pty", { input: input + "\n" });
      setInput("");
    } catch (e: any) {
      setOutput((prev) => prev + `\n[Error writing to PTY: ${e.toString()}]\n`);
    }
  };

  // PTYの停止
  const handleStop = async () => {
    try {
      await invoke("stop_pty");
      setStatus("stopped");
    } catch (e: any) {
      setOutput((prev) => prev + `\n[Error stopping PTY: ${e.toString()}]\n`);
    }
  };

  return (
    <main className="container" style={{ padding: "20px", fontFamily: "sans-serif" }}>
      <h1>PTY Connection Stream Test</h1>

      {/* 起動設定パネル */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "15px", flexWrap: "wrap" }}>
        <label>
          Command:
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            style={{ marginLeft: "5px", padding: "5px" }}
            disabled={status === "running"}
          />
        </label>
        <label>
          Args (space separated):
          <input
            value={args}
            placeholder="e.g. -l"
            onChange={(e) => setArgs(e.target.value)}
            style={{ marginLeft: "5px", padding: "5px" }}
            disabled={status === "running"}
          />
        </label>
        <label>
          CWD:
          <input
            value={cwd}
            placeholder="Absolute folder path"
            onChange={(e) => setCwd(e.target.value)}
            style={{ marginLeft: "5px", padding: "5px", width: "200px" }}
            disabled={status === "running"}
          />
        </label>
        {status === "running" ? (
          <button onClick={handleStop} style={{ padding: "5px 15px", backgroundColor: "#ff4d4d", color: "#fff", border: "none", borderRadius: "3px", cursor: "pointer" }}>
            Stop PTY
          </button>
        ) : (
          <button onClick={handleStart} style={{ padding: "5px 15px", backgroundColor: "#4caf50", color: "#fff", border: "none", borderRadius: "3px", cursor: "pointer" }}>
            Start PTY
          </button>
        )}
      </div>

      {/* ステータス表示 */}
      <div style={{ marginBottom: "10px" }}>
        Status: <strong style={{ color: status === "running" ? "#4caf50" : "#ff4d4d" }}>{status.toUpperCase()}</strong>
      </div>

      {/* PTY 出力ログ表示エリア */}
      <pre
        ref={outputRef}
        style={{
          width: "100%",
          height: "400px",
          backgroundColor: "#1e1e1e",
          color: "#00ff00",
          padding: "10px",
          overflowY: "scroll",
          borderRadius: "5px",
          fontFamily: "monospace",
          fontSize: "14px",
          textAlign: "left",
          whiteSpace: "pre-wrap",
        }}
      >
        {output || "[PTY Output Log will appear here]"}
      </pre>

      {/* コマンド入力エリア */}
      <form onSubmit={handleSend} style={{ display: "flex", gap: "10px", marginTop: "15px" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type command and press Enter..."
          style={{ flexGrow: "1", padding: "10px", fontSize: "16px", borderRadius: "3px", border: "1px solid #ccc" }}
          disabled={status !== "running"}
        />
        <button type="submit" style={{ padding: "10px 25px", fontSize: "16px", backgroundColor: "#2196f3", color: "#fff", border: "none", borderRadius: "3px", cursor: "pointer" }} disabled={status !== "running"}>
          Send
        </button>
      </form>
    </main>
  );
}

export default App;
