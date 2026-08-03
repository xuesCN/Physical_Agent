import { expect, test } from "@playwright/test";
import { createStreamingFrameBatcher } from "../src/streamingFrameBatcher";

/**
 * Manual frame queue: the batcher's contract is "at most one flush per frame",
 * not "60 flushes per second", so the tests drive frames explicitly instead of
 * depending on a real refresh rate, timers or browser paints.
 *
 * Cancelled frames stay callable via `forceRun` so the tests can simulate a
 * stale frame that the environment still fires after a terminal event.
 */
function createManualFrames() {
  const callbacks = new Map<number, () => void>();
  const live = new Set<number>();
  let nextHandle = 1;

  return {
    requestFrame(callback: () => void): number {
      const handle = nextHandle;
      nextHandle += 1;
      callbacks.set(handle, callback);
      live.add(handle);
      return handle;
    },
    cancelFrame(handle: number): void {
      live.delete(handle);
    },
    /** Every frame ever requested, cancelled or not. */
    requested(): number {
      return callbacks.size;
    },
    /** Frames still queued to run. */
    pending(): number {
      return live.size;
    },
    handles(): number[] {
      return [...callbacks.keys()];
    },
    runPending(): void {
      const handles = [...live];
      live.clear();
      for (const handle of handles) {
        callbacks.get(handle)?.();
      }
    },
    forceRun(handle: number): void {
      live.delete(handle);
      callbacks.get(handle)?.();
    }
  };
}

function setup() {
  const frames = createManualFrames();
  let flushes = 0;
  const batcher = createStreamingFrameBatcher({
    flush: () => {
      flushes += 1;
    },
    requestFrame: (callback) => frames.requestFrame(callback),
    cancelFrame: (handle) => frames.cancelFrame(handle)
  });
  return { frames, batcher, flushCount: () => flushes };
}

test("C7 batcher collapses a burst of schedules into a single frame and flush", () => {
  const { frames, batcher, flushCount } = setup();

  batcher.schedule();
  batcher.schedule();
  batcher.schedule();

  // Three deltas in one frame must queue one frame and paint nothing yet.
  expect(frames.requested()).toBe(1);
  expect(frames.pending()).toBe(1);
  expect(flushCount()).toBe(0);

  frames.runPending();
  expect(flushCount()).toBe(1);

  // The next burst queues a fresh frame rather than reusing the spent one.
  batcher.schedule();
  batcher.schedule();
  expect(frames.requested()).toBe(2);

  frames.runPending();
  expect(flushCount()).toBe(2);
});

test("C7 batcher settle flushes pending content once and neutralises the stale frame", () => {
  const { frames, batcher, flushCount } = setup();

  batcher.schedule();
  expect(frames.pending()).toBe(1);

  // An early stream end must paint the buffered tail synchronously.
  batcher.settle();
  expect(flushCount()).toBe(1);
  expect(frames.pending()).toBe(0);

  // A frame the environment still fires afterwards must not repaint.
  frames.forceRun(frames.handles()[0]);
  expect(flushCount()).toBe(1);

  // Settling with nothing buffered is a no-op.
  batcher.settle();
  expect(flushCount()).toBe(1);
});

test("C7 batcher cancel discards pending content and stays reusable", () => {
  const { frames, batcher, flushCount } = setup();

  batcher.schedule();
  batcher.cancel();

  // Terminal events carry the authoritative content, so nothing is painted.
  expect(flushCount()).toBe(0);
  expect(frames.pending()).toBe(0);

  frames.forceRun(frames.handles()[0]);
  expect(flushCount()).toBe(0);

  // Cancelling must not wedge the batcher for a later stream.
  batcher.schedule();
  frames.runPending();
  expect(flushCount()).toBe(1);
});

test("a stale cancelled frame cannot consume a newly scheduled generation", () => {
  const { frames, batcher, flushCount } = setup();

  batcher.schedule();
  const staleHandle = frames.handles()[0];
  batcher.cancel();
  batcher.schedule();

  frames.forceRun(staleHandle);
  expect(flushCount()).toBe(0);
  expect(frames.pending()).toBe(1);

  frames.runPending();
  expect(flushCount()).toBe(1);
  expect(frames.pending()).toBe(0);
});

test("a stale settled frame cannot consume a newly scheduled generation", () => {
  const { frames, batcher, flushCount } = setup();

  batcher.schedule();
  const staleHandle = frames.handles()[0];
  batcher.settle();
  expect(flushCount()).toBe(1);
  batcher.schedule();

  frames.forceRun(staleHandle);
  expect(flushCount()).toBe(1);
  expect(frames.pending()).toBe(1);

  frames.runPending();
  expect(flushCount()).toBe(2);
  expect(frames.pending()).toBe(0);
});
