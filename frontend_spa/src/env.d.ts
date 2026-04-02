export {};

declare global {
  interface Window {
    __TAPNE_FRONTEND_CONFIG__?: Record<string, unknown>;
  }
}
