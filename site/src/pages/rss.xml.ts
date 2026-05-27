import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import type { APIContext } from "astro";
import { REPO_URL, withBase, BASE_URL } from "@/config";
import { loadAuthorsCache } from "@/lib/registry";

export async function GET(context: APIContext) {
  const notebooks = await getCollection("notebooks");
  const authorsCache = loadAuthorsCache();
  const siteUrl = context.site!;
  // Include base path in site URL for correct channel link
  const siteWithBase = new URL(BASE_URL, siteUrl).href;
  const feedUrl = new URL(withBase("/rss.xml"), siteUrl).href;

  // Sort by date descending (undated entries last)
  const sorted = [...notebooks].sort((a, b) => {
    const da = a.data.date ? new Date(a.data.date).getTime() : 0;
    const db = b.data.date ? new Date(b.data.date).getTime() : 0;
    return db - da;
  });

  // Derive lastBuildDate from most recent entry
  const latestDate = sorted.find((n) => n.data.date)?.data.date;
  const lastBuildDate = latestDate
    ? new Date(latestDate).toUTCString()
    : new Date().toUTCString();

  return rss({
    title: "Forgebook",
    description:
      "A notebook-first AI cookbook. Jupyter notebook examples and tutorials.",
    site: siteWithBase,
    xmlns: {
      atom: "http://www.w3.org/2005/Atom",
    },
    items: sorted.map((notebook) => {
      // Resolve author display names from authors.yaml
      const authorNames = notebook.data.authors
        .map((a) => authorsCache[a.github]?.name ?? a.github)
        .join(", ");

      return {
        title: notebook.data.title,
        // Only include pubDate when the entry has an explicit date
        ...(notebook.data.date
          ? { pubDate: new Date(notebook.data.date) }
          : {}),
        description: notebook.data.description || "",
        // Absolute URL for NLWeb compatibility (used as document identifier)
        link: new URL(withBase(`/notebook/${notebook.data.slug}/`), siteUrl)
          .href,
        categories: notebook.data.tags || [],
        author: authorNames,
      };
    }),
    customData: `<language>en-us</language>
<lastBuildDate>${lastBuildDate}</lastBuildDate>
<atom:link href="${feedUrl}" rel="self" type="application/rss+xml"/>
<docs>${REPO_URL}</docs>`,
    stylesheet: withBase("/rss/styles.xsl"),
  });
}
