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
