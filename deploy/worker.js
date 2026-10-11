/**
 * epel.cloud website Worker.
 *
 * Serves the static cookbook (hosted on Cloudflare Pages) for an explicit
 * allowlist of website paths, and passes EVERYTHING else through to the
 * existing origin (the Fedora mirror) completely untouched.
 *
 * Deployed together with TWO routes (see docs/deploy.md):
 *   epel.cloud/pub/*  -> no script (mirror traffic never invokes a Worker)
 *   epel.cloud/*      -> this script
 *
 * Rollback = delete both routes; the zone then behaves exactly as before.
 */

const PAGES_HOST = "epel-cloud.pages.dev";

const EXACT_PATHS = new Set([
  "/",
  "/mirror",
  "/recipes",
  "/robots.txt",
  "/sitemap.xml",
  "/favicon.ico",
  "/404.html",
]);

const PREFIX_PATHS = ["/recipes/", "/assets/"];

function isWebsitePath(pathname) {
  if (EXACT_PATHS.has(pathname)) return true;
  return PREFIX_PATHS.some((prefix) => pathname.startsWith(prefix));
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (!isWebsitePath(url.pathname)) {
      // Mirror or unknown path: hand off to the origin unchanged, preserving
      // redirects, errors, Range behavior and all existing cache semantics.
      return fetch(request);
    }

    const pagesUrl = new URL(url);
    pagesUrl.hostname = PAGES_HOST;
    const response = await fetch(pagesUrl.toString(), {
      method: request.method,
      headers: request.headers,
      redirect: "manual",
    });

    // Pages may redirect (e.g. /recipes/ -> /recipes). Keep the visitor on
    // epel.cloud rather than exposing the pages.dev hostname.
    const location = response.headers.get("location");
    if (location) {
      const rewritten = new URL(location, pagesUrl);
      if (rewritten.hostname === PAGES_HOST) {
        rewritten.hostname = url.hostname;
        const headers = new Headers(response.headers);
        headers.set("location", rewritten.toString());
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers,
        });
      }
    }

    return response;
  },
};
