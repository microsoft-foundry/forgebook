/**
 * Site configuration constants
 * Centralized config to avoid hardcoded values across the codebase
 */

/** GitHub repository URL */
export const REPO_URL = "https://github.com/your-org/forgebook";

/** Base URL path for deployment (from Astro config) */
export const BASE_URL = import.meta.env.BASE_URL;

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
