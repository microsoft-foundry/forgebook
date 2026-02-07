import { defineCollection } from "astro:content";
import { z } from "astro/zod";
import fs from "node:fs";
import path from "node:path";
import yaml from "yaml";
import type { Loader } from "astro/loaders";

// Define the Author schema
const authorSchema = z.object({
  github: z.string(),
});

// Custom loader that reads from registry.yaml and loads notebook content
function registryLoader(): Loader {
  return {
    name: "registry-loader",
    load: async ({ store, logger, parseData }) => {
      const repoRoot = path.resolve(import.meta.dirname, "../..");
      const registryPath = path.join(repoRoot, "registry.yaml");

      if (!fs.existsSync(registryPath)) {
        logger.warn("registry.yaml not found");
        return;
      }

      const registryContent = fs.readFileSync(registryPath, "utf-8");
      const entries = yaml.parse(registryContent) as Array<{
        slug: string;
        path: string;
        title: string;
        description?: string;
        date?: string;
        authors: Array<{ github: string }>;
        tags?: string[];
      }>;

      // Load allowed tags
      const tagsPath = path.join(repoRoot, "tags.yaml");
      const tagsContent = fs.readFileSync(tagsPath, "utf-8");
      const allowedTags = new Set<string>(yaml.parse(tagsContent) as string[]);

      store.clear();

      for (const entry of entries) {
        const notebookPath = path.join(repoRoot, entry.path);

        if (!fs.existsSync(notebookPath)) {
          logger.warn(`Notebook not found: ${entry.path}`);
          continue;
        }

        if (entry.tags) {
          const unknownTags = entry.tags.filter(t => !allowedTags.has(t));
          if (unknownTags.length > 0) {
            logger.warn(`Unknown tags in ${entry.slug}: ${unknownTags.join(", ")}`);
          }
        }

        const notebookContent = fs.readFileSync(notebookPath, "utf-8");
        const notebookJson = JSON.parse(notebookContent);

        const data = await parseData({
          id: entry.slug,
          data: {
            ...entry,
            notebook: notebookJson,
          },
        });

        store.set({
          id: entry.slug,
          data,
        });
      }

      logger.info(`Loaded ${entries.length} notebooks from registry`);
    },
    schema: z.object({
      slug: z.string(),
      path: z.string(),
      title: z.string(),
      description: z.string().optional(),
      date: z.string().optional(),
      authors: z.array(authorSchema),
      tags: z.array(z.string()).optional(),
      notebook: z.any(), // The raw notebook JSON
    }),
  };
}

// Define the notebooks collection using our custom loader
const notebooks = defineCollection({
  loader: registryLoader(),
});

export const collections = { notebooks };

