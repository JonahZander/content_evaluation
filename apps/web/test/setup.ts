import "@testing-library/jest-dom/vitest";

class MockEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(_: string) {}

  close() {}
}

Object.defineProperty(globalThis, "EventSource", {
  configurable: true,
  writable: true,
  value: MockEventSource,
});
