import fs from "node:fs";
import path from "node:path";
import yaml from "yaml";
import { REPO_URL } from "@/config";

export interface Author {
  github: string;
}

export interface AuthorInfo {
  name: string;
  title: string;
  avatar?: string;
  githubUrl?: string;
  linkedinUrl?: string;
  xUrl?: string;
}

export interface ResolvedAuthor {
  github: string;
  name: string;
  title: string;
  avatar: string;
  githubUrl?: string;
  linkedinUrl?: string;
  xUrl?: string;
}

// Find repo root by searching upward for authors.yaml
function findRepoRoot(): string {
  let dir = import.meta.dirname;
  // Try up to 10 levels
  for (let i = 0; i < 10; i++) {
    if (fs.existsSync(path.join(dir, "authors.yaml"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break; // Reached filesystem root
    dir = parent;
  }
  // Fallback: assume cwd is site/, go up one level
  return path.resolve(process.cwd(), "..");
}

const REPO_ROOT = findRepoRoot();

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

  if (!cached?.name || !cached?.title) {
    throw new Error(
      `Author "${author.github}" must have name and title defined in authors.yaml`
    );
  }

  const githubUrl = cached.githubUrl || `https://github.com/${author.github}`;
  return {
    github: author.github,
    name: cached.name,
    title: cached.title,
    avatar: cached.avatar || `https://github.com/${author.github}.png?size=200`,
    githubUrl,
    linkedinUrl: cached.linkedinUrl,
    xUrl: cached.xUrl,
  };
}

export async function resolveAuthors(
  authors: Author[]
): Promise<ResolvedAuthor[]> {
  const cache = loadAuthorsCache();
  return Promise.all(authors.map((a) => resolveAuthor(a, cache)));
}
