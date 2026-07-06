import { describe, expect, it } from "vitest";
import { subscribeToTauriEvent } from "./tauriListener";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("subscribeToTauriEvent", () => {
  it("unlistens once the registration resolves after normal cleanup", async () => {
    const { promise, resolve } = deferred<() => void>();
    let called = 0;
    const unlisten = () => called++;

    const cleanup = subscribeToTauriEvent(promise);
    resolve(unlisten);
    await promise;

    expect(called).toBe(0);
    cleanup();
    expect(called).toBe(1);
  });

  it("does not leak a listener when cleanup runs before registration resolves", async () => {
    // Regression guard: this is the exact race that let a duplicate
    // "pty-output" listener survive React StrictMode's dev-mode
    // mount->cleanup->mount, causing every PTY chunk to be written to the
    // terminal twice (visually duplicated/garbled output).
    const { promise, resolve } = deferred<() => void>();
    let called = 0;
    const unlisten = () => called++;

    const cleanup = subscribeToTauriEvent(promise);
    cleanup(); // runs before the promise resolves
    resolve(unlisten);
    await promise;

    expect(called).toBe(1);
  });

  it("never calls the underlying unlisten function more than once", async () => {
    const { promise, resolve } = deferred<() => void>();
    let called = 0;
    resolve(() => called++);

    const cleanup = subscribeToTauriEvent(promise);
    await promise;
    cleanup();
    cleanup();

    expect(called).toBe(1);
  });
});
