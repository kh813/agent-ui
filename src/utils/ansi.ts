/**
 * Regular expression to match ANSI escape codes.
 * Standard terminators include all alphabetic characters, ~, @, =, >, <, etc.
 */
const ANSI_REGEX = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[a-zA-Z~@>=><]/g;

/**
 * Strips all ANSI escape codes from a given string.
 */
export function stripAnsi(text: string): string {
  return text.replace(ANSI_REGEX, "");
}

/**
 * Cleans up raw terminal output to be more human-readable in a chat bubble.
 * Removes backspaces, carriage returns, and strips ANSI codes.
 */
export function cleanTerminalOutput(text: string): string {
  let cleaned = stripAnsi(text);
  
  // Remove non-printable raw control chars (excluding backspace \x08) and unicode replacement character (tofu/☒)
  cleaned = cleaned.replace(/[\x00-\x07\x0B-\x0C\x0E-\x1F\x7F\uFFFD]/g, "");
  
  // Remove braille patterns (loading spinners)
  cleaned = cleaned.replace(/[\u2800-\u28FF]/g, "");
  
  // Remove proprietary terminal escape fragments (like '4m0;1u', '4;2m1;1u', etc.)
  cleaned = cleaned.replace(/\b\d+m\d+;\d+u/g, "");
  cleaned = cleaned.replace(/\b\d+;\d+m\d+;\d+u/g, "");
  cleaned = cleaned.replace(/\b\d+;\d+u/g, "");
  cleaned = cleaned.replace(/[a-zA-Z\d]+;\d+u/g, "");
  
  // Remove other raw terminal garbage sequence leftovers globally (inline)
  cleaned = cleaned.replace(/W4;/g, "");
  cleaned = cleaned.replace(/4;\s*q/g, "");
  cleaned = cleaned.replace(/4;/g, "");
  cleaned = cleaned.replace(/\bq\b/g, "");
  cleaned = cleaned.replace(/\bX\b/g, "");
  cleaned = cleaned.replace(/\bW4\b/g, "");
  
  // Normalize carriage returns and line feeds
  cleaned = cleaned.replace(/\r\n/g, "\n");
  cleaned = cleaned.replace(/\r/g, "");
  
  // Split into lines to filter out system prompt/nav rows completely
  const lines = cleaned.split("\n");
  const filteredLines = lines.filter((line) => {
    const trimmed = line.trim();
    if (!trimmed) return true; // Keep empty lines for spacing
    
    // Filter out active REPL prompt indicators
    if (trimmed.includes("? for shortcuts") || trimmed.includes("shortcutsX") || trimmed.includes("shortcuts")) return false;
    
    // Filter out Generating progress indicators (including prefix states like 'Gene', 'Gener' etc.)
    const lowerTrimmed = trimmed.toLowerCase();
    const targetGenerating = "generating...";
    if (lowerTrimmed.length > 0 && lowerTrimmed.length <= targetGenerating.length && targetGenerating.startsWith(lowerTrimmed)) {
      return false;
    }
    if (trimmed.includes("●") || trimmed.includes("ListPermissions") || trimmed.includes("ListDir") || trimmed.includes("workspace(s)")) return false;
    if (trimmed.includes("Tip:") || trimmed.includes("Use /skills to browse") || trimmed.includes("└")) return false;
    if (trimmed.includes("ctrl+o to expand") || trimmed.includes("ctrl+") || trimmed.includes("expand)") || trimmed.includes("expand")) return false;
    if (trimmed.includes("Flash (Medium)") || trimmed.includes("Medium)")) return false;
    
    // Filter out short garbage dot rows or 1-2 char alphabetic leftovers
    if (/^\.+$/.test(trimmed)) return false;
    if (/^[a-zA-Z]{1,2}$/.test(trimmed)) return false;
    
    // Filter out models, workspace metadata and headers
    if (trimmed.includes("Gemini 3.5") || trimmed.includes("Gemini")) return false;
    if (trimmed.includes("Google AI Pro") || trimmed.includes("Google AI")) return false;
    if (trimmed.includes("Antigravity CLI") || trimmed.includes("Welcome to the Antigravity")) return false;
    if (trimmed.includes("Signing in") || trimmed.includes("Accessing workspace")) return false;
    if (trimmed.includes("Yes, I trust") || trimmed.includes("No, exit") || trimmed.includes("Navigate") || trimmed.includes("Confirm")) return false;
    
    // Filter out emails
    if (trimmed.includes("@") && (trimmed.includes(".com") || trimmed.includes(".org") || trimmed.includes(".net") || trimmed.includes(".edu"))) return false;
    
    // Filter out workspace directory paths
    if (trimmed.includes("~/") || trimmed.includes("/Users/") || trimmed.includes("src-tauri") || trimmed.includes("chatui")) return false;
    
    // Remove divider borders (like '──────────') or lines containing mostly divider dashes
    if (trimmed.includes("──") || trimmed.includes("───")) return false;
    if (/^[─\-_=\*]{3,}$/.test(trimmed)) return false;
    
    // Remove terminal size / mouse query fragments and standalone bracket leaks (like 'W4;', '4; q', '4;', 'q', 'X', '[1', '[1;')
    if (/^[A-Za-z\d]*\d+;[A-Za-z\d]*;*[A-Za-z\d]*$/.test(trimmed)) return false;
    if (/^[a-zA-Z\d];\s*[a-zA-Z\d]$/.test(trimmed)) return false;
    if (/^\[\d+;*$/.test(trimmed)) return false;
    if (trimmed === "W4;" || trimmed === "4; q" || trimmed === "4;" || trimmed === "q" || trimmed === "X" || trimmed === "[1" || trimmed === "[1;") return false;
    
    return true;
  });
  
  cleaned = filteredLines.join("\n");
  
  // Simulate backspaces using hex code \x08 to avoid regex word-boundary (\b) confusion
  while (cleaned.includes("\x08")) {
    const prevLength = cleaned.length;
    cleaned = cleaned.replace(/[^\x08]\x08/, "");
    
    // Prevent infinite loop if backspace is at the start of the string (no character preceding it)
    if (cleaned.length === prevLength) {
      cleaned = cleaned.replace(/\x08/, "");
    }
  }
  
  return cleaned;
}
