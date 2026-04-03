// Production-only stub for lovable/src/lib/devMock.ts.
//
// In the external override build (frontend_spa/vite.production.config.ts),
// "@/lib/devMock" is aliased to this file.  That excludes the real
// devMock.ts — and all of lovable/src/data/mockData.ts — from the
// production bundle.
//
// api.ts only calls resolveMockRequest when IS_DEV_MODE is true.
// IS_DEV_MODE is always false in production because Django injects
// window.TAPNE_RUNTIME_CONFIG into the HTML shell before the bundle loads.
// This function is therefore unreachable dead code in production, but it
// must exist so the import in api.ts type-checks correctly.

export function resolveMockRequest(
  _method: string,
  _url: string,
  _body?: unknown,
): unknown {
  return {};
}
