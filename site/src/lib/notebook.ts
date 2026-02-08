import nb from "notebookjs";
import Prism from "prismjs";
import { JSDOM } from "jsdom";
import DOMPurify from "dompurify";
import { marked } from "marked";
import markedFootnote from "marked-footnote";
import katex from "katex";

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

export function renderNotebook(notebookJson: unknown, title?: string, description?: string): string {
  try {
    // Reset iframe storage for this notebook
    currentIframes = new Map<string, string>();
    
    const notebook = nb.parse(notebookJson);
    const rendered = notebook.render(dom.window.document);
    
    // Sanitize HTML to prevent XSS attacks
    const purify = DOMPurify(dom.window);
    const sanitized = purify.sanitize(rendered.outerHTML);
    
    // Restore preserved trusted iframes
    let result = restoreIframes(sanitized, currentIframes);

    // Strip the first H1 only if it matches the page title (already shown in header)
    if (title) {
      const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      result = result.replace(
        new RegExp(
          `(<div class="nb-cell nb-markdown-cell">)\\s*<h1>${escaped}<\\/h1>`
        ),
        "$1"
      );
    }

    // Strip italic subtitle if it matches the registry description (shown in page body)
    if (description) {
      const escaped = description.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      result = result.replace(
        new RegExp(`<p><em>${escaped}<\\/em><\\/p>`),
        ""
      );
    }

    return result;
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
