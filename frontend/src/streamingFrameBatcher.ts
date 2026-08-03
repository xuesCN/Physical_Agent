/**
 * Coalesces high-frequency streaming updates into at most one flush per
 * animation frame.
 *
 * A fast model emits hundreds of chat deltas per second; calling the React
 * state setter for each one re-renders the dashboard subtree that often. The
 * batcher lets callers accumulate text themselves and simply announce "there is
 * something to paint", collapsing any number of announcements inside one frame
 * into a single `flush()`.
 *
 * The frame API is injectable so tests can drive a manual queue instead of
 * depending on a real refresh rate.
 */

export interface StreamingFrameBatcherOptions {
  /** Called at most once per animation frame while updates are pending. */
  flush: () => void;
  requestFrame?: (callback: () => void) => number;
  cancelFrame?: (handle: number) => void;
}

export interface StreamingFrameBatcher {
  /** Marks content dirty and ensures exactly one frame is queued. */
  schedule: () => void;
  /**
   * Cancels the queued frame and flushes any pending content immediately.
   * Used when a stream ends without a terminal event, so the last tokens are
   * never dropped. A stale frame that still runs afterwards must not flush.
   */
  settle: () => void;
  /**
   * Cancels the queued frame and discards pending content. Used on the
   * `done` / `aborted` / `error` paths, where the terminal payload already
   * carries the authoritative content.
   */
  cancel: () => void;
}

export function createStreamingFrameBatcher({
  flush,
  requestFrame = (callback) => requestAnimationFrame(callback),
  cancelFrame = (handle) => cancelAnimationFrame(handle)
}: StreamingFrameBatcherOptions): StreamingFrameBatcher {
  let frameHandle: number | null = null;
  let flushPending = false;
  let nextGeneration = 0;
  let activeGeneration: number | null = null;

  const flushNow = () => {
    if (!flushPending) {
      return;
    }
    flushPending = false;
    flush();
  };

  const runFrame = (generation: number) => {
    if (activeGeneration !== generation) {
      return;
    }
    frameHandle = null;
    activeGeneration = null;
    flushNow();
  };

  const clearFrame = () => {
    if (frameHandle !== null) {
      cancelFrame(frameHandle);
      frameHandle = null;
    }
    activeGeneration = null;
  };

  return {
    schedule() {
      flushPending = true;
      if (frameHandle === null) {
        const generation = nextGeneration + 1;
        nextGeneration = generation;
        activeGeneration = generation;
        frameHandle = requestFrame(() => runFrame(generation));
      }
    },
    settle() {
      clearFrame();
      flushNow();
    },
    cancel() {
      clearFrame();
      flushPending = false;
    }
  };
}
