import type { UnlistenFn } from "@tauri-apps/api/event";

// Wraps a pending `listen(...)` registration so it can be safely torn down
// from a React effect's cleanup function.
//
// `listen()` returns a Promise<UnlistenFn> because registration is async.
// The naive pattern -
//   let unlisten: UnlistenFn | null = null;
//   listen(...).then((fn) => { unlisten = fn; });
//   return () => unlisten?.();
// - leaks the listener whenever cleanup runs before the promise resolves
// (e.g. React StrictMode's dev-only mount->cleanup->mount, or any effect
// whose dependencies change again quickly): `unlisten` is still null when
// cleanup runs, so the cleanup is a no-op, and the in-flight registration
// completes moments later with nothing left to ever call it. Two live
// listeners then both fire for every subsequent event, e.g. writing every
// PTY output chunk to the terminal twice.
export function subscribeToTauriEvent(pending: Promise<UnlistenFn>): () => void {
  let disposed = false;
  let unlisten: UnlistenFn | null = null;

  pending.then((fn) => {
    if (disposed) {
      fn();
      return;
    }
    unlisten = fn;
  });

  return () => {
    disposed = true;
    unlisten?.();
    unlisten = null;
  };
}
