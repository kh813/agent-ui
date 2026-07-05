import assert from "node:assert";
import { stripAnsi, cleanTerminalOutput } from "./ansi";

console.log("Running ANSI utilities unit tests via Node.js assert...");

// Test 1: Strip ANSI color codes
const coloredText = "\u001b[31mRed Text\u001b[0m";
assert.strictEqual(stripAnsi(coloredText), "Red Text");

const boldBlueText = "\x1B[1;34mBold Blue\x1B[0m";
assert.strictEqual(stripAnsi(boldBlueText), "Bold Blue");
console.log("✓ Test 1: stripAnsi passed");

// Test 2: Clean backspaces
assert.strictEqual(cleanTerminalOutput("abc\b"), "ab");
assert.strictEqual(cleanTerminalOutput("hello\b\b\b\b\bworld"), "world");
assert.strictEqual(cleanTerminalOutput("loading...\b\b\bdone"), "loadingdone");
console.log("✓ Test 2: cleanTerminalOutput (backspaces) passed");

// Test 3: Normalize carriage returns
assert.strictEqual(cleanTerminalOutput("line1\r\nline2"), "line1\nline2");
assert.strictEqual(cleanTerminalOutput("line1\rline2"), "line1\nline2");
console.log("✓ Test 3: cleanTerminalOutput (carriage returns) passed");

console.log("All frontend utility tests passed successfully!");
