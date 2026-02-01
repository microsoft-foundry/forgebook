import fs from "node:fs";
import path from "node:path";
import yaml from "yaml";
import { REPO_URL } from "@/config";

export interface Author {
  github: string;
}

export interface AuthorInfo {
  name?: string;
  website?: string;
  avatar?: string;
}

export interface ResolvedAuthor {
  github: string;
  name: string;
  avatar: string;
  profileUrl: string;
}

const REPO_ROOT = path.resolve(import.meta.dirname, "../../../");

export function loadAuthorsCache(): Record<string, AuthorInfo> {
  const authorsPath = path.join(REPO_ROOT, "authors.yaml");
  if (!fs.existsSync(authorsPath)) {
    return {};
  }
  const content = fs.readFileSync(authorsPath, "utf-8");
  return yaml.parse(content) || {};
}

export function getGitHubNotebookUrl(notebookPath: string): string {
  return `${REPO_URL}/blob/main/${notebookPath}`;
}

export async function resolveAuthor(
  author: Author,
  cache: Record<string, AuthorInfo>
): Promise<ResolvedAuthor> {
  const cached = cache[author.github];

  if (cached?.name && cached?.avatar) {
    return {
      github: author.github,
      name: cached.name,
      avatar: cached.avatar,
      profileUrl: cached.website || `https://github.com/${author.github}`,
    };
  }

  // Fallback to GitHub API or direct avatar URL
  // In production, this would fetch from GitHub API
  // For now, use the direct avatar URL pattern
  return {
    github: author.github,
    name: cached?.name || `@${author.github}`,
    avatar:
      cached?.avatar || `https://github.com/${author.github}.png?size=200`,
    profileUrl: cached?.website || `https://github.com/${author.github}`,
  };
}

export async function resolveAuthors(
  authors: Author[]
): Promise<ResolvedAuthor[]> {
  const cache = loadAuthorsCache();
  return Promise.all(authors.map((a) => resolveAuthor(a, cache)));
}
