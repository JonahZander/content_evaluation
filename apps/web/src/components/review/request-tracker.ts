export interface RequestTracker {
  abort: () => void;
  isCurrent: (requestId: number) => boolean;
  start: () => { signal: AbortSignal; requestId: number };
}

export function createRequestTracker(): RequestTracker {
  let abortController: AbortController | null = null;
  let requestId = 0;

  return {
    abort() {
      abortController?.abort();
    },
    isCurrent(currentRequestId: number) {
      return requestId === currentRequestId;
    },
    start() {
      abortController?.abort();
      const controller = new AbortController();
      abortController = controller;
      requestId += 1;
      return { signal: controller.signal, requestId };
    },
  };
}
