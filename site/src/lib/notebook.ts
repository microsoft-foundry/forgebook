import nb from "notebookjs";
import Prism from "prismjs";
import { JSDOM } from "jsdom";
import DOMPurify from "dompurify";
import { marked } from "marked";
import markedFootnote from "marked-footnote";
import katex from "katex";
import path from "node:path";

// Load common Prism languages
import "prismjs/components/prism-python";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";

// KaTeX renderer for math expressions
function renderMath(text: string): string {
  // Block math: $$ ... $$
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => {
    try {
      return katex.renderToString(math.trim(), { displayMode: true, throwOnError: false });
    } catch {
      return `<pre class="katex-error">${math}</pre>`;
    }
  });
  
  // Inline math: $ ... $ (but not $$ or currency like $100)
  text = text.replace(/\$([^\$\n]+?)\$/g, (match, math) => {
    // Skip if it looks like currency
    if (/^\d/.test(math)) return match;
    try {
      return katex.renderToString(math.trim(), { displayMode: false, throwOnError: false });
    } catch {
      return match;
    }
  });
  
  return text;
}

// Trusted video embed domains for iframe allowlisting
const trustedDomains = [
  "youtube.com",
  "www.youtube.com",
  "youtube-nocookie.com",
  "www.youtube-nocookie.com",
  "player.vimeo.com",
];

// Pre-process to preserve trusted iframes from markdown content
function preserveIframes(text: string): { text: string; iframes: Map<string, string> } {
  const iframes = new Map<string, string>();
  let counter = 0;
  
  // Match iframes and replace with placeholders
  const processed = text.replace(/<iframe[^>]*>[\s\S]*?<\/iframe>/gi, (match) => {
    // Only preserve if from trusted domain
    const srcMatch = match.match(/src=["']([^"']+)["']/i);
    if (srcMatch) {
      const src = srcMatch[1];
      const isAllowed = trustedDomains.some((domain) => src.includes(domain));
      if (isAllowed) {
        // Use a span with data attribute as placeholder (survives DOMPurify)
        const placeholder = `<span data-iframe-placeholder="${counter}"></span>`;
        iframes.set(`data-iframe-placeholder="${counter}"`, match);
        counter++;
        return placeholder;
      }
    }
    return ''; // Remove untrusted iframes
  });
  
  return { text: processed, iframes };
}

// Restore iframes after markdown processing and sanitization
function restoreIframes(html: string, iframes: Map<string, string>): string {
  let result = html;
  for (const [placeholder, iframe] of iframes) {
    // Replace the span placeholder with the iframe in a responsive container
    result = result.replace(
      new RegExp(`<span ${placeholder}></span>`, 'g'),
      `<div class="aspect-video my-4">${iframe}</div>`
    );
  }
  return result;
}

// Configure marked with extensions
marked.use(markedFootnote());

// Configure marked for GitHub Flavored Markdown
marked.setOptions({
  gfm: true, // GitHub Flavored Markdown (tables, task lists, strikethrough)
  breaks: false, // Don't add <br> on single line breaks
});

// Configure notebookjs for Node.js environment
const dom = new JSDOM("");

// Store iframes during markdown processing
let currentIframes = new Map<string, string>();

nb.markdown = (text: string) => {
  // Preserve trusted iframes before markdown parsing
  const { text: withoutIframes, iframes } = preserveIframes(text);
  // Store for later restoration
  currentIframes = new Map([...currentIframes, ...iframes]);
  // Render math, then parse markdown
  const withMath = renderMath(withoutIframes);
  return marked.parse(withMath) as string;
};

// Set up syntax highlighting
nb.highlighter = (
  text: string,
  pre: HTMLPreElement,
  code: HTMLElement,
  lang: string
) => {
  const language = lang || "python";
  pre.className = `language-${language}`;
  if (code) {
    code.className = `language-${language}`;
  }
  const grammar = Prism.languages[language];
  return grammar ? Prism.highlight(text, grammar, language) : text;
};

export interface NotebookCell {
  type: "markdown" | "code";
  source: string;
  outputs?: string[];
}

/**
 * Rewrite relative asset paths so they resolve correctly on the published site.
 *
 * Notebook markdown cells use paths relative to the notebook file, e.g. `media/foo.png`.
 * On the site the page lives at `/base/notebook/<slug>/`, so the browser would wrongly
 * resolve that to `/base/notebook/<slug>/media/foo.png`.
 *
 * Notebook assets are served from `public/notebook/` which mirrors `notebooks/` in the
 * repo, so we resolve each relative src against the notebook's directory, strip the
 * leading `notebooks/` prefix, and prepend `<basePath>/notebook/` to build the correct
 * absolute URL.
 */
function rewriteAssetPaths(html: string, notebookPath: string, basePath: string): string {
  // Directory of the notebook relative to the repo root, e.g. "notebooks" or "notebooks/examples"
  const notebookDir = path.posix.dirname(notebookPath.replace(/\\/g, "/"));

  // Normalise basePath: ensure it has no trailing slash
  const base = basePath.replace(/\/$/, "");

  const isAbsoluteOrSpecial = (url: string) => /^(https?:\/\/|\/|data:|#|mailto:|tel:|javascript:)/i.test(url);
  const resolveAsset = (url: string): string => {
    // Resolve relative to the notebook's directory, e.g.
    //   notebookDir = "notebooks", src = "media/foo.png" → "notebooks/media/foo.png"
    //   notebookDir = "notebooks/examples", src = "../media/foo.png" → "notebooks/media/foo.png"
    const resolved = path.posix.normalize(path.posix.join(notebookDir, url));

    // Strip leading "notebooks/" to get the path under public/notebook/
    const underPublic = resolved.replace(/^notebooks\//, "");

    return `${base}/notebook/${underPublic}`;
  };

  let result = html.replace(
    /(<(?:img|video|audio|source|track)\b[^>]*\bsrc=["'])([^"']+)(["'])/gi,
    (_match, prefix: string, src: string, suffix: string) => {
      // Skip absolute URLs, data URIs, and protocol-relative URLs
      if (isAbsoluteOrSpecial(src)) return _match;

      return `${prefix}${resolveAsset(src)}${suffix}`;
    }
  );

  result = result.replace(
    /(<a\b[^>]*\bhref=["'])([^"']+)(["'])/gi,
    (_match, prefix: string, href: string, suffix: string) => {
      // Only rewrite direct links to notebook assets. Other relative links are handled elsewhere.
      if (isAbsoluteOrSpecial(href)) return _match;
      if (!/\.(?:png|jpe?g|gif|webp|svg|mp4|webm|mov|mp3|wav|m4a|csv|json|jsonl|txt|pdf)(?:[?#].*)?$/i.test(href)) {
        return _match;
      }

      return `${prefix}${resolveAsset(href)}${suffix}`;
    }
  );

  return result;
}

const calloutTypes = {
  note: {
    title: "Note",
    iconPath: "M12.002 1.999c5.523 0 10.001 4.478 10.001 10.002c0 5.523-4.478 10.001-10.001 10.001C6.478 22.002 2 17.524 2 12.001C2 6.477 6.478 1.999 12.002 1.999m0 1.5a8.502 8.502 0 1 0 0 17.003a8.502 8.502 0 0 0 0-17.003M12 10.5a.75.75 0 0 1 .75.75v5a.75.75 0 0 1-1.5 0v-5a.75.75 0 0 1 .75-.75M12 9a1 1 0 1 0 0-2a1 1 0 0 0 0 2",
  },
  tip: {
    title: "Tip",
    iconPath: "M12 2.001a7.25 7.25 0 0 1 7.25 7.25c0 2.096-.9 4.02-2.663 5.742a.75.75 0 0 0-.175.265l-.032.103l-1.13 4.895a2.25 2.25 0 0 1-2.02 1.737l-.173.007h-2.114a2.25 2.25 0 0 1-2.147-1.577l-.045-.167l-1.13-4.895a.75.75 0 0 0-.206-.368c-1.68-1.64-2.577-3.463-2.659-5.444l-.006-.298l.004-.24A7.25 7.25 0 0 1 12 2.002M14.115 18.5H9.884l.329 1.42a.75.75 0 0 0 .627.573l.103.008h2.114a.75.75 0 0 0 .7-.483l.03-.099zM12 3.501a5.75 5.75 0 0 0-5.746 5.53l-.004.22l.007.277c.076 1.563.8 3.02 2.206 4.392c.264.258.46.576.571.926l.049.178l.455 1.975h4.923l.458-1.976a2.25 2.25 0 0 1 .493-.97l.127-.133c1.404-1.373 2.128-2.828 2.204-4.392l.007-.277l-.004-.22A5.75 5.75 0 0 0 12 3.5",
  },
  important: {
    title: "Important",
    iconPath: "M12 2.002a3.875 3.875 0 0 0-3.875 3.875c0 2.92 1.207 6.552 1.813 8.199a2.19 2.19 0 0 0 2.064 1.423c.904 0 1.739-.542 2.063-1.418c.606-1.64 1.81-5.254 1.81-8.204A3.875 3.875 0 0 0 12 2.002M9.625 5.877a2.375 2.375 0 0 1 4.75 0c0 2.655-1.111 6.043-1.717 7.684a.69.69 0 0 1-.655.438a.69.69 0 0 1-.657-.44c-.607-1.652-1.721-5.058-1.721-7.682m2.376 11.124a2.501 2.501 0 1 0 0 5.002a2.501 2.501 0 0 0 0-5.002M11 19.502a1.001 1.001 0 1 1 2.002 0a1.001 1.001 0 0 1-2.002 0",
  },
  caution: {
    title: "Caution",
    iconPath: "M12 2c5.523 0 10 4.478 10 10s-4.477 10-10 10S2 17.522 2 12S6.477 2 12 2m0 1.667c-4.595 0-8.333 3.738-8.333 8.333S7.405 20.333 12 20.333s8.333-3.738 8.333-8.333S16.595 3.667 12 3.667m-.001 10.835a.999.999 0 1 1 0 1.998a.999.999 0 0 1 0-1.998M11.994 7a.75.75 0 0 1 .744.648l.007.101l.004 4.502a.75.75 0 0 1-1.493.103l-.007-.102l-.004-4.501a.75.75 0 0 1 .75-.751",
  },
  warning: {
    title: "Warning",
    iconPath: "M9.138 3.707c1.228-2.276 4.494-2.276 5.721 0l6.743 12.502c1.168 2.165-.4 4.792-2.86 4.793H5.255c-2.46 0-4.028-2.628-2.86-4.793zm4.4.712c-.66-1.225-2.419-1.225-3.08 0L3.715 16.921a1.75 1.75 0 0 0 1.54 2.581h13.487a1.75 1.75 0 0 0 1.54-2.581zM12 15a1 1 0 1 1 0 2a1 1 0 0 1 0-2m0-7.5a.75.75 0 0 1 .75.75v4.5a.75.75 0 0 1-1.5 0v-4.5A.75.75 0 0 1 12 7.5",
  },
} as const;

type CalloutType = keyof typeof calloutTypes;

/**
 * Upgrade portable Markdown callouts into semantic, styleable HTML.
 *
 * Authors can write normal Jupyter-compatible Markdown like:
 *
 * > **Tip:** Keep the source image stable.
 * > More supporting detail.
 *
 * In plain Markdown viewers this remains a blockquote. On Forgebook, the leading
 * bold label becomes a callout title while the remaining paragraph text stays as body copy.
 */
function enhanceCallouts(html: string): string {
  const template = dom.window.document.createElement("template");
  template.innerHTML = html;
  const svgNamespace = "http://www.w3.org/2000/svg";

  template.content.querySelectorAll("blockquote").forEach((blockquote) => {
    const firstParagraph = blockquote.querySelector(":scope > p");
    const firstElement = firstParagraph?.firstElementChild;
    if (!firstParagraph || !firstElement || !["STRONG", "B"].includes(firstElement.tagName)) {
      return;
    }

    const label = firstElement.textContent?.trim().replace(/:$/, "").toLowerCase();
    if (!label || !(label in calloutTypes)) {
      return;
    }

    const type = label as CalloutType;
    const { title, iconPath } = calloutTypes[type];

    blockquote.classList.add("notebook-callout", `notebook-callout-${type}`);
    blockquote.setAttribute("data-callout", type);
    blockquote.setAttribute("aria-label", `${title} callout`);

    const heading = dom.window.document.createElement("div");
    heading.className = "notebook-callout-title";

    const iconElement = dom.window.document.createElement("span");
    iconElement.className = "notebook-callout-icon";
    iconElement.setAttribute("aria-hidden", "true");

    const iconSvg = dom.window.document.createElementNS(svgNamespace, "svg");
    iconSvg.setAttribute("viewBox", "0 0 24 24");
    iconSvg.setAttribute("fill", "none");
    iconSvg.setAttribute("focusable", "false");

    const iconPathElement = dom.window.document.createElementNS(svgNamespace, "path");
    iconPathElement.setAttribute("fill", "currentColor");
    iconPathElement.setAttribute("d", iconPath);
    iconSvg.appendChild(iconPathElement);
    iconElement.appendChild(iconSvg);

    const titleElement = dom.window.document.createElement("strong");
    titleElement.textContent = title;

    heading.append(iconElement, titleElement);
    blockquote.insertBefore(heading, firstParagraph);

    firstElement.remove();
    const firstNode = firstParagraph.firstChild;
    if (firstNode?.nodeType === dom.window.Node.TEXT_NODE) {
      firstNode.textContent = firstNode.textContent?.replace(/^\s+/, "") ?? "";
    }
    if (!firstParagraph.textContent?.trim() && firstParagraph.children.length === 0) {
      firstParagraph.remove();
    }
  });

  return template.innerHTML;
}

/**
 * Rewrite relative `.ipynb` links so they point to the rendered notebook pages.
 *
 * Notebook markdown cells link to sibling notebooks with relative paths like
 * `foundry-agent-part-1.ipynb`. On the site these need to become
 * `<basePath>/notebook/<slug>/` where slug is derived from the filename.
 */
function rewriteNotebookLinks(html: string, notebookPath: string, basePath: string): string {
  const notebookDir = path.posix.dirname(notebookPath.replace(/\\/g, "/"));
  const base = basePath.replace(/\/$/, "");

  return html.replace(
    /(<a\b[^>]*\bhref=["'])([^"']+\.ipynb)(["'])/gi,
    (_match, prefix: string, href: string, suffix: string) => {
      // Skip absolute URLs
      if (/^(https?:\/\/|\/|data:|#)/.test(href)) return _match;

      // Resolve relative to the notebook's directory and extract the slug
      const resolved = path.posix.normalize(path.posix.join(notebookDir, href));
      const slug = path.posix.basename(resolved, ".ipynb");

      return `${prefix}${base}/notebook/${slug}/${suffix}`;
    }
  );
}

export function renderNotebook(notebookJson: unknown, notebookPath: string, basePath: string): string {
  try {
    // Reset iframe storage for this notebook
    currentIframes = new Map<string, string>();
    
    const notebook = nb.parse(notebookJson);
    const rendered = notebook.render(dom.window.document);
    
    // Sanitize HTML to prevent XSS attacks
    const purify = DOMPurify(dom.window);
    let sanitized = purify.sanitize(rendered.outerHTML);
    // Fix double-encoded entities in code blocks (Prism encodes <> then DOMPurify re-encodes)
    sanitized = sanitized.replaceAll("&amp;lt;", "&lt;").replaceAll("&amp;gt;", "&gt;").replaceAll("&amp;amp;", "&amp;");
    
    // Restore preserved trusted iframes
    let result = restoreIframes(sanitized, currentIframes);

    // Rewrite relative asset paths to absolute URLs
    result = rewriteAssetPaths(result, notebookPath, basePath);

    // Upgrade portable blockquote callouts to styled callout elements
    result = enhanceCallouts(result);

    // Rewrite relative .ipynb links to site notebook pages
    return rewriteNotebookLinks(result, notebookPath, basePath);
  } catch (error) {
    console.error("Error rendering notebook:", error);
    return `<div class="text-red-500">Error rendering notebook</div>`;
  }
}

export function extractMarkdown(notebookJson: unknown): string {
  const notebook = notebookJson as {
    cells: Array<{
      cell_type: string;
      source: string | string[];
    }>;
  };

  if (!notebook.cells) {
    return "";
  }

  return notebook.cells
    .map((cell) => {
      const source = Array.isArray(cell.source)
        ? cell.source.join("")
        : cell.source;

      if (cell.cell_type === "markdown") {
        return source;
      } else if (cell.cell_type === "code") {
        return "```python\n" + source + "\n```";
      }
      return "";
    })
    .join("\n\n");
}
