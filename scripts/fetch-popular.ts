/**
 * Queries Azure Application Insights for the most-viewed production recipes
 * and writes the results to site/src/data/popular.json.
 *
 * Uses Azure AD (Entra ID) authentication via DefaultAzureCredential,
 * which automatically picks up OIDC tokens from GitHub Actions or
 * local Azure CLI credentials for development.
 *
 * Required env vars:
 *   APP_INSIGHTS_RESOURCE_ID  — Full Azure resource ID for the App Insights instance
 *                               e.g. /subscriptions/{sub}/resourceGroups/{rg}/providers/microsoft.insights/components/{name}
 *
 * Optional:
 *   POPULAR_DAYS        — Ranking window in days (default: 30)
 *   POPULAR_LIMIT       — Max notebooks to include (default: 6)
 *   POPULAR_SINCE       — Inclusive UTC view-count start (default: 2026-06-02T00:00:00Z)
 *   POPULAR_HOST        — Production hostname (default: microsoft-foundry.github.io)
 *   POPULAR_BASE_PATH   — Production site base path (default: /forgebook)
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { DefaultAzureCredential } from "@azure/identity";
import { LogsQueryClient } from "@azure/monitor-query-logs";
import yaml from "yaml";

interface PopularEntry {
  slug: string;
  views: number;
  recentViews: number;
}

interface RegistryEntry {
  slug: string;
}

const RESOURCE_ID = process.env.APP_INSIGHTS_RESOURCE_ID;
const DAYS = Number(process.env.POPULAR_DAYS) || 30;
const LIMIT = Number(process.env.POPULAR_LIMIT) || 6;
const SINCE = process.env.POPULAR_SINCE || "2026-06-02T00:00:00Z";
const HOST = process.env.POPULAR_HOST || "microsoft-foundry.github.io";
const BASE_PATH = (process.env.POPULAR_BASE_PATH || "/forgebook").replace(/\/+$/, "");

const OUTPUT_PATH = resolve(
  import.meta.dirname ?? ".",
  "../site/src/data/popular.json"
);
const REGISTRY_PATH = resolve(import.meta.dirname ?? ".", "../registry.yaml");

const registry = yaml.parse(readFileSync(REGISTRY_PATH, "utf-8")) as RegistryEntry[];
const publishedSlugs = registry.map(({ slug }) => slug);
const kustoSlugs = JSON.stringify(publishedSlugs);
const recipePathPattern = `^${BASE_PATH.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/notebook/([^/]+)/?$`;
const query = `
let publishedSlugs = dynamic(${kustoSlugs});
pageViews
| where timestamp >= datetime(${SINCE})
| extend parsedUrl = parse_url(tostring(url))
| extend host = tolower(tostring(parsedUrl.Host)), path = tostring(parsedUrl.Path)
| where host == "${HOST.toLowerCase()}"
| extend slug = extract(@"${recipePathPattern}", 1, path)
| where isnotempty(slug) and slug in (publishedSlugs)
| summarize sinceLaunchViews = count(), recentViews = countif(timestamp > ago(${DAYS}d)) by slug
| where recentViews > 0
| order by recentViews desc, sinceLaunchViews desc, slug asc
| take ${LIMIT}
`;

async function main(): Promise<void> {
  if (!RESOURCE_ID) {
    throw new Error("APP_INSIGHTS_RESOURCE_ID is required");
  }

  const sinceDate = new Date(SINCE);
  if (Number.isNaN(sinceDate.getTime())) {
    throw new Error(`POPULAR_SINCE must be an ISO 8601 timestamp: ${SINCE}`);
  }

  const queryDays = Math.max(DAYS, Math.ceil((Date.now() - sinceDate.getTime()) / 86_400_000) + 1);
  const credential = new DefaultAzureCredential();
  const client = new LogsQueryClient(credential);

  const result = await client.queryResource(RESOURCE_ID, query, {
    duration: `P${queryDays}D`,
  });

  if (result.status !== "Success") {
    throw new Error(
      `App Insights query failed: ${JSON.stringify(result.error)}`
    );
  }

  const rows = result.tables[0]?.rows ?? [];
  const notebooks: PopularEntry[] = rows.map((row) => ({
    slug: row[0] as string,
    views: row[1] as number,
    recentViews: row[2] as number,
  }));

  console.log(
    `[fetch-popular] Found ${notebooks.length} popular recipes ranked by the last ${DAYS} days.`
  );

  writeOutput({
    metricVersion: "recipe-page-views-v1",
    updatedAt: new Date().toISOString(),
    since: sinceDate.toISOString(),
    rankingWindowDays: DAYS,
    notebooks,
  });
}

function writeOutput(payload: {
  metricVersion: "recipe-page-views-v1";
  updatedAt: string;
  since: string;
  rankingWindowDays: number;
  notebooks: PopularEntry[];
}): void {
  mkdirSync(dirname(OUTPUT_PATH), { recursive: true });
  writeFileSync(OUTPUT_PATH, JSON.stringify(payload, null, 2) + "\n");
  console.log(`[fetch-popular] Wrote ${OUTPUT_PATH}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
