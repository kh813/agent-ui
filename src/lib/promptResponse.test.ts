import { describe, expect, it } from "vitest";
import { resolvePromptResponseInput } from "./promptResponse";

const ESC = String.fromCharCode(0x1b);

describe("resolvePromptResponseInput", () => {
  it("sends a bare carriage return for the default (first) option", () => {
    expect(resolvePromptResponseInput("Yes, I trust this folder")).toBe("\r");
    expect(resolvePromptResponseInput("Yes")).toBe("\r");
  });

  it("moves down one option before confirming for the second option", () => {
    expect(resolvePromptResponseInput("No, exit")).toBe(`${ESC}[B\r`);
    expect(resolvePromptResponseInput("always allow in this conversation")).toBe(`${ESC}[B\r`);
  });

  it("moves down two options before confirming for the third option", () => {
    expect(resolvePromptResponseInput("always allow (Persist to settings.json)")).toBe(`${ESC}[B${ESC}[B\r`);
    expect(resolvePromptResponseInput("Persist to settings.json")).toBe(`${ESC}[B${ESC}[B\r`);
  });

  it("moves down three options before confirming for the fourth option", () => {
    expect(resolvePromptResponseInput("No")).toBe(`${ESC}[B${ESC}[B${ESC}[B\r`);
  });

  it("emits an actual ESC control byte, not the literal two-character text '[B'", () => {
    // Regression guard: a prior refactor accidentally dropped the ESC prefix
    // here, turning the arrow-down sequence into inert literal text that
    // agy's own prompt UI ignored, silently breaking every button except
    // "Yes".
    const result = resolvePromptResponseInput("No, exit");
    expect(result.charCodeAt(0)).toBe(0x1b);
    expect(result).not.toBe("[B\r");
  });

  it("falls back to the raw text plus newline for freeform/path responses", () => {
    expect(resolvePromptResponseInput("/Users/me/some/project")).toBe("/Users/me/some/project\n");
  });
});
