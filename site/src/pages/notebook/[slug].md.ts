import type { APIRoute, GetStaticPaths } from "astro";
import { getCollection } from "astro:content";
import { extractMarkdown } from "@/lib/notebook";

export const getStaticPaths: GetStaticPaths = async () => {
  const notebooks = await getCollection("notebooks");
  return notebooks.map((notebook) => ({
    params: { slug: notebook.data.slug },
    props: { notebook },
  }));
};

export const GET: APIRoute = async ({ props }) => {
  const { notebook } = props as {
    notebook: { data: { notebook: unknown } };
  };
  const markdown = extractMarkdown(notebook.data.notebook);

  return new Response(markdown, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
};
