/**
 * Regular expression to match ANSI escape codes.
 */
const ANSI_REGEX = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;

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
  
  // Remove braille patterns (loading spinners)
  cleaned = cleaned.replace(/[\u2800-\u28FF]/g, "");
  
  // Remove proprietary terminal escape fragments (like '4m0;1u', '4;2m1;1u', etc.)
  cleaned = cleaned.replace(/\b\d+m\d+;\d+u/g, "");
  cleaned = cleaned.replace(/\b\d+;\d+m\d+;\d+u/g, "");
  cleaned = cleaned.replace(/\b\d+;\d+u/g, "");
  cleaned = cleaned.replace(/[a-zA-Z\d]+;\d+u/g, "");
  
  // Normalize carriage returns and line feeds
  cleaned = cleaned.replace(/\r\n/g, "\n");
  cleaned = cleaned.replace(/\r/g, "\n");
  
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
