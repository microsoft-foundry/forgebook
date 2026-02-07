/**
 * Queries Azure Application Insights for the most-clicked notebook cards
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
 *   POPULAR_DAYS   — Lookback window in days (default: 30)
 *   POPULAR_LIMIT  — Max notebooks to include (default: 6)
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { DefaultAzureCredential } from "@azure/identity";
import { LogsQueryClient } from "@azure/monitor-query-logs";

interface PopularEntry {
  slug: string;
  clicks: number;
}

const RESOURCE_ID = process.env.APP_INSIGHTS_RESOURCE_ID;
const DAYS = Number(process.env.POPULAR_DAYS) || 30;
const LIMIT = Number(process.env.POPULAR_LIMIT) || 6;

const OUTPUT_PATH = resolve(
  import.meta.dirname ?? ".",
  "../site/src/data/popular.json"
);

const query = `
customEvents
| where timestamp > ago(${DAYS}d)
| where name == "Click"
| where tostring(customDimensions.label) startswith "notebook-card:"
| extend slug = replace_string(tostring(customDimensions.label), "notebook-card:", "")
| summarize clicks = count() by slug
| order by clicks desc
| take ${LIMIT}
`;

async function main(): Promise<void> {
  if (!RESOURCE_ID) {
    console.warn(
      "[fetch-popular] APP_INSIGHTS_RESOURCE_ID not set — writing empty popular.json."
    );
    writeOutput({ updatedAt: new Date().toISOString(), notebooks: [] });
    return;
  }

  const credential = new DefaultAzureCredential();
  const client = new LogsQueryClient(credential);

  const result = await client.queryResource(RESOURCE_ID, query, {
    duration: `P${DAYS}D`,
  });

  if (result.status !== "Success") {
    throw new Error(
      `App Insights query failed: ${JSON.stringify(result.error)}`
    );
  }

  const rows = result.tables[0]?.rows ?? [];
  const notebooks: PopularEntry[] = rows.map((row) => ({
    slug: row[0] as string,
    clicks: row[1] as number,
  }));

  console.log(
    `[fetch-popular] Found ${notebooks.length} popular notebooks (last ${DAYS} days).`
  );

  writeOutput({ updatedAt: new Date().toISOString(), notebooks });
}

function writeOutput(payload: {
  updatedAt: string;
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
