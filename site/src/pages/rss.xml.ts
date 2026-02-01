import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import type { APIContext } from "astro";
import { REPO_URL, withBase } from "@/config";

export async function GET(context: APIContext) {
  const notebooks = await getCollection("notebooks");

  return rss({
    title: "Forgebook",
    description:
      "A notebook-first AI cookbook. Jupyter notebook examples and tutorials.",
    site: context.site!,
    items: notebooks.map((notebook) => ({
      title: notebook.data.title,
      pubDate: notebook.data.date
        ? new Date(notebook.data.date)
        : new Date(),
      description: notebook.data.description || "",
      link: withBase(`/notebook/${notebook.data.slug}/`),
      categories: notebook.data.tags || [],
      author: notebook.data.authors.map((a) => a.github).join(", "),
    })),
    customData: `<language>en-us</language>
<docs>${REPO_URL}</docs>`,
    stylesheet: "/rss/styles.xsl",
  });
}
