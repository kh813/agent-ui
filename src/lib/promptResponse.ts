// ANSI cursor-down sequence (ESC [ B). Built via fromCharCode rather than a
// "\x1b"-style escape in a string literal so it can't be silently mangled by
// an editor/formatter stripping "invisible" control characters again - that
// exact loss previously turned this into a literal "[B" that did nothing.
const ARROW_DOWN = String.fromCharCode(0x1b) + "[B";

// Maps a prompt-response button's label to the literal bytes written to the
// PTY. These CLI prompts (folder trust, tool permission) are keyboard-only -
// there's no way to select a non-default option directly - so reaching one
// means sending N arrow-down presses to move off the default-selected first
// option, then \r to confirm it.
export function resolvePromptResponseInput(responseText: string): string {
  if (responseText === "Yes, I trust this folder" || responseText === "Yes") {
    return "\r";
  }
  if (responseText === "No, exit") {
    return ARROW_DOWN + "\r";
  }
  if (responseText.includes("always allow in this conversation")) {
    return ARROW_DOWN + "\r";
  }
  if (
    responseText.includes("always allow (Persist to settings.json)") ||
    responseText.includes("Persist to settings.json")
  ) {
    return ARROW_DOWN + ARROW_DOWN + "\r";
  }
  if (responseText === "No") {
    return ARROW_DOWN + ARROW_DOWN + ARROW_DOWN + "\r";
  }
  return responseText + "\n";
}
