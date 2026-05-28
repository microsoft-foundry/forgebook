/**
 * Site configuration constants
 * Centralized config to avoid hardcoded values across the codebase
 */

/** GitHub repository URL */
export const REPO_URL = "https://github.com/microsoft-foundry/forgebook";

/** Base URL path for deployment (from Astro config) */
export const BASE_URL = import.meta.env.BASE_URL;

/** Site-wide positioning and discovery metadata */
export const SITE = {
  name: "Forgebook",
  formalName: "Microsoft Foundry Forgebook",
  defaultTitle: "Forgebook | Microsoft Foundry notebook recipes",
  tagline: "Your cookbook for building AI with Microsoft Foundry.",
  description:
    "Forgebook is a Microsoft Foundry cookbook of runnable Jupyter notebook recipes, hands-on AI guides, and examples for building agents, model inference, and multimodal apps.",
  keywords: [
    "Microsoft Foundry",
    "Foundry cookbook",
    "AI cookbook",
    "Jupyter notebook recipes",
    "AI recipes",
    "agent recipes",
    "model inference",
    "multimodal AI",
    "hands-on AI guides",
    "developer tutorials",
  ],
  socialImage: {
    path: "/images/og/forgebook.png",
    width: 1200,
    height: 630,
    alt: "Forgebook logo with the text: Your cookbook for building AI with Microsoft Foundry.",
  },
} as const;

/**
 * Get the GitHub URL for a notebook file
 */
export function getGitHubFileUrl(filePath: string): string {
  return `${REPO_URL}/blob/main/${filePath}`;
}

/**
 * Prepend base URL to a path for internal navigation
 */
export function withBase(path: string): string {
  // Remove leading slash from path if present to avoid double slashes
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  // BASE_URL already has trailing slash in Astro
  const base = BASE_URL.endsWith("/") ? BASE_URL.slice(0, -1) : BASE_URL;
  return `${base}/${cleanPath}`;
}

/**
 * Create an absolute URL for metadata and share crawlers.
 *
 * Relative site paths are prefixed with Astro's base path. Paths that already
 * include the base path are preserved to avoid `/forgebook/forgebook/...`.
 */
export function absoluteSiteUrl(pathOrUrl: string, site: URL | string): string {
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl;

  const base = BASE_URL.endsWith("/") ? BASE_URL.slice(0, -1) : BASE_URL;
  const pathWithBase = pathOrUrl === base || pathOrUrl.startsWith(`${base}/`)
    ? pathOrUrl
    : withBase(pathOrUrl);

  return new URL(pathWithBase, site).href;
}
