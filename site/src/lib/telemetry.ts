/**
 * Application Insights telemetry for client-side monitoring.
 *
 * Tracks page views, user sessions, unhandled errors,
 * button/link clicks, and scroll depth.
 *
 * The connection string is read from the PUBLIC_APP_INSIGHTS_CONNECTION_STRING
 * environment variable at build time (Astro embeds PUBLIC_* vars into the bundle).
 */
import { ApplicationInsights } from "@microsoft/applicationinsights-web";

let appInsights: ApplicationInsights | null = null;

export function initTelemetry(): ApplicationInsights | null {
  const connectionString = import.meta.env.PUBLIC_APP_INSIGHTS_CONNECTION_STRING;

  if (!connectionString) {
    console.warn("[telemetry] PUBLIC_APP_INSIGHTS_CONNECTION_STRING not set — skipping App Insights initialization.");
    return null;
  }

  if (appInsights) return appInsights;

  appInsights = new ApplicationInsights({
    config: {
      connectionString,
      enableAutoRouteTracking: true,   // Track SPA-style navigations
      disableFetchTracking: false,     // Track fetch requests
      enableCorsCorrelation: false,    // Avoid CORS issues on static sites
      disableAjaxTracking: false,      // Track XMLHttpRequests
      autoTrackPageVisitTime: true,    // Track time spent on pages
    },
  });

  appInsights.loadAppInsights();
  appInsights.trackPageView();

  trackClicks(appInsights);
  trackScrollDepth(appInsights);

  return appInsights;
}

export function getAppInsights(): ApplicationInsights | null {
  return appInsights;
}

// ---------------------------------------------------------------------------
// Click tracking
// ---------------------------------------------------------------------------

/** Tracks clicks on buttons, links, and elements with [data-track-click]. */
function trackClicks(ai: ApplicationInsights): void {
  document.addEventListener("click", (e) => {
    const target = (e.target as HTMLElement)?.closest<HTMLElement>(
      "button, a, [data-track-click]"
    );
    if (!target) return;

    const label =
      target.getAttribute("data-track-click") ||
      target.getAttribute("aria-label") ||
      target.textContent?.trim().slice(0, 80) ||
      "unknown";

    const tag = target.tagName.toLowerCase();
    const href = (target as HTMLAnchorElement).href || undefined;

    ai.trackEvent({
      name: "Click",
      properties: {
        label,
        tag,
        href,
        page: location.pathname,
      },
    });
  });
}

// ---------------------------------------------------------------------------
// Scroll depth tracking
// ---------------------------------------------------------------------------

/** Fires custom events at 25 / 50 / 75 / 100 % scroll thresholds (once each per page). */
function trackScrollDepth(ai: ApplicationInsights): void {
  const thresholds = [25, 50, 75, 100];
  const reached = new Set<number>();

  function getScrollPercent(): number {
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (docHeight <= 0) return 100;
    return Math.round((window.scrollY / docHeight) * 100);
  }

  function onScroll(): void {
    const pct = getScrollPercent();
    for (const t of thresholds) {
      if (pct >= t && !reached.has(t)) {
        reached.add(t);
        ai.trackEvent({
          name: "ScrollDepth",
          properties: {
            threshold: t,
            page: location.pathname,
          },
        });
      }
    }

    // All thresholds hit — stop listening
    if (reached.size === thresholds.length) {
      window.removeEventListener("scroll", onScroll, { capture: true } as EventListenerOptions);
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
}
