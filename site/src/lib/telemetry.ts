/**
 * Application Insights telemetry for client-side monitoring.
 *
 * Tracks page views, user sessions, unhandled errors,
 * button/link clicks, scroll depth, search queries,
 * share/copy actions, theme changes, tag filtering,
 * outbound links, and Core Web Vitals.
 *
 * The connection string is read from the PUBLIC_APP_INSIGHTS_CONNECTION_STRING
 * environment variable at build time (Astro embeds PUBLIC_* vars into the bundle).
 *
 * ## Usage from Astro module scripts
 *   import { trackEvent, trackError } from "@/lib/telemetry";
 *   trackEvent("MyEvent", { key: "value" });
 *
 * ## Usage from inline scripts (is:inline)
 *   window.__telemetry?.trackEvent("MyEvent", { key: "value" });
 */
import { ApplicationInsights, SeverityLevel } from "@microsoft/applicationinsights-web";

let appInsights: ApplicationInsights | null = null;

// ---------------------------------------------------------------------------
// Public helpers — safe to call even before init (calls are no-ops)
// ---------------------------------------------------------------------------

/** Track a named custom event with optional properties. */
export function trackEvent(name: string, properties?: Record<string, unknown>): void {
  appInsights?.trackEvent({ name, properties: { page: location.pathname, ...properties } });
  recordTestTelemetry({
    data: {
      baseType: "EventData",
      baseData: {
        name,
        properties: { page: location.pathname, ...properties },
      },
    },
  });
}

/** Track an exception with optional context properties. */
export function trackError(error: unknown, properties?: Record<string, string>): void {
  const err = error instanceof Error ? error : new Error(String(error));
  appInsights?.trackException({
    exception: err,
    severityLevel: SeverityLevel.Error,
    properties: { page: location.pathname, ...properties },
  });
}

/** Track a numeric metric (e.g. Core Web Vitals). */
export function trackMetric(name: string, average: number, properties?: Record<string, string>): void {
  appInsights?.trackMetric({ name, average, properties: { page: location.pathname, ...properties } });
  recordTestTelemetry({
    data: {
      baseType: "MetricData",
      baseData: {
        metrics: [{ name, value: average }],
        properties: { page: location.pathname, ...properties },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

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
      disableCookiesUsage: true,       // Avoid setting Forgebook-specific browser cookies
    },
  });

  appInsights.loadAppInsights();
  appInsights.trackPageView();
  recordTestTelemetry({
    data: {
      baseType: "PageviewData",
      baseData: {
        properties: { page: location.pathname },
      },
    },
  });

  trackClicks(appInsights);
  trackScrollDepth(appInsights);
  trackWebVitals();
  exposeGlobalBridge();

  return appInsights;
}

export function getAppInsights(): ApplicationInsights | null {
  return appInsights;
}

// ---------------------------------------------------------------------------
// Global bridge for inline scripts (is:inline cannot use ES imports)
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    __telemetry?: {
      trackEvent: typeof trackEvent;
      trackError: typeof trackError;
      trackMetric: typeof trackMetric;
      /** Flush the SDK buffer — useful for testing and devtools debugging. */
      flush: () => void;
    };
    /** Test-only hook populated by Playwright before page scripts run. */
    __forgebookTelemetryTestCapture?: Array<Record<string, unknown>>;
  }
}

function recordTestTelemetry(envelope: Record<string, unknown>): void {
  window.__forgebookTelemetryTestCapture?.push(envelope);
}

function exposeGlobalBridge(): void {
  window.__telemetry = {
    trackEvent,
    trackError,
    trackMetric,
    flush: () => { appInsights?.flush(); },
  };
}

// ---------------------------------------------------------------------------
// Click tracking — distinguishes outbound links
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

    // Distinguish outbound (external) links from internal clicks
    const isOutbound = href ? new URL(href, location.origin).origin !== location.origin : false;

    const name = isOutbound ? "OutboundClick" : "Click";
    const properties = {
      label,
      tag,
      href,
      page: location.pathname,
      ...(isOutbound && { destination: new URL(href!, location.origin).hostname }),
    };

    ai.trackEvent({ name, properties });
    recordTestTelemetry({
      data: {
        baseType: "EventData",
        baseData: { name, properties },
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
        recordTestTelemetry({
          data: {
            baseType: "EventData",
            baseData: {
              name: "ScrollDepth",
              properties: {
                threshold: t,
                page: location.pathname,
              },
            },
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

// ---------------------------------------------------------------------------
// Core Web Vitals (LCP, INP, CLS, FCP, TTFB)
// ---------------------------------------------------------------------------

async function trackWebVitals(): Promise<void> {
  try {
    const { onLCP, onINP, onCLS, onFCP, onTTFB } = await import("web-vitals");

    const send = ({ name, value, rating }: { name: string; value: number; rating: string }) => {
      trackMetric(`WebVital_${name}`, value, { rating });
    };

    onLCP(send);
    onINP(send);
    onCLS(send);
    onFCP(send);
    onTTFB(send);
  } catch {
    // web-vitals not available — skip silently
  }
}
