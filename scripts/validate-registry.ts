#!/usr/bin/env node

/**
 * Validates the registry.yaml file:
 * - All required fields present
 * - Paths point to existing files
 * - Slugs are unique
 * - GitHub usernames are valid format
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "yaml";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

interface Author {
  github: string;
}

interface NotebookEntry {
  slug: string;
  path: string;
  title: string;
  authors: Author[];
  description?: string;
  date?: string;
  tags?: string[];
}

function loadRegistry(): NotebookEntry[] {
  const registryPath = path.join(REPO_ROOT, "registry.yaml");
  const content = fs.readFileSync(registryPath, "utf-8");
  return yaml.parse(content) as NotebookEntry[];
}

function validateSlug(slug: string): boolean {
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug);
}

function validateGitHubUsername(username: string): boolean {
  return /^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$/.test(username);
}

function validateNotebookPath(notebookPath: string): boolean {
  return /^notebooks\/.*\.ipynb$/.test(notebookPath);
}

function main(): void {
  console.log("Validating registry.yaml...\n");

  const errors: string[] = [];
  const warnings: string[] = [];
  const entries = loadRegistry();

  const tagsPath = path.join(REPO_ROOT, "tags.yaml");
  const tagsContent = fs.readFileSync(tagsPath, "utf-8");
  const allowedTags = new Set<string>(yaml.parse(tagsContent) as string[]);

  if (!Array.isArray(entries)) {
    console.error("❌ Registry must be an array of entries");
    process.exit(1);
  }

  const slugs = new Set<string>();

  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const prefix = `Entry ${i + 1} (${entry.slug || "no slug"})`;

    // Required fields
    if (!entry.slug) {
      errors.push(`${prefix}: Missing required field 'slug'`);
    } else if (!validateSlug(entry.slug)) {
      errors.push(
        `${prefix}: Invalid slug format '${entry.slug}'. Use lowercase letters, numbers, and hyphens.`
      );
    } else if (slugs.has(entry.slug)) {
      errors.push(`${prefix}: Duplicate slug '${entry.slug}'`);
    } else {
      slugs.add(entry.slug);
    }

    if (!entry.path) {
      errors.push(`${prefix}: Missing required field 'path'`);
    } else if (!validateNotebookPath(entry.path)) {
      errors.push(
        `${prefix}: Path must start with 'notebooks/' and end with '.ipynb'`
      );
    } else {
      const fullPath = path.join(REPO_ROOT, entry.path);
      if (!fs.existsSync(fullPath)) {
        errors.push(`${prefix}: Notebook file not found: ${entry.path}`);
      }
    }

    if (!entry.title) {
      errors.push(`${prefix}: Missing required field 'title'`);
    } else if (entry.title.length > 60) {
      warnings.push(
        `${prefix}: Title is ${entry.title.length} chars (max 60 recommended to avoid 3-line wrap on card grid)`
      );
    }

    if (entry.description && entry.description.length > 200) {
      warnings.push(
        `${prefix}: Description is ${entry.description.length} chars (max 200 recommended to avoid overflow on card grid)`
      );
    }

    if (!entry.authors || !Array.isArray(entry.authors)) {
      errors.push(`${prefix}: Missing required field 'authors'`);
    } else if (entry.authors.length === 0) {
      errors.push(`${prefix}: Authors array must have at least one entry`);
    } else {
      for (const author of entry.authors) {
        if (!author.github) {
          errors.push(`${prefix}: Author missing 'github' field`);
        } else if (!validateGitHubUsername(author.github)) {
          errors.push(
            `${prefix}: Invalid GitHub username '${author.github}'`
          );
        }
      }
    }

    // Optional field validation
    if (entry.date && !/^\d{4}-\d{2}-\d{2}$/.test(entry.date)) {
      warnings.push(
        `${prefix}: Date should be in YYYY-MM-DD format, got '${entry.date}'`
      );
    }

    if (entry.tags) {
      for (const tag of entry.tags) {
        if (!validateSlug(tag)) {
          errors.push(
            `${prefix}: Tag '${tag}' must use lowercase letters, numbers, and hyphens`
          );
        } else if (!allowedTags.has(tag)) {
          errors.push(
            `${prefix}: Unknown tag '${tag}'. Allowed tags: ${[...allowedTags].join(", ")}`
          );
        }
      }
    }
  }

  // Print results
  if (warnings.length > 0) {
    console.log("⚠️  Warnings:");
    for (const warning of warnings) {
      console.log(`   ${warning}`);
    }
    console.log();
  }

  if (errors.length > 0) {
    console.log("❌ Errors:");
    for (const error of errors) {
      console.log(`   ${error}`);
    }
    console.log();
    console.log(`Validation failed with ${errors.length} error(s)`);
    process.exit(1);
  }

  console.log(`✅ Validated ${entries.length} notebook(s) successfully`);
}

main();
