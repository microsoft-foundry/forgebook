import nb from "notebookjs";
import Prism from "prismjs";
import { JSDOM } from "jsdom";
import DOMPurify from "dompurify";

// Load common Prism languages
import "prismjs/components/prism-python";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";

// Configure notebookjs for Node.js environment
const dom = new JSDOM("");
nb.markdown = (text: string) => {
  // Simple markdown to HTML conversion
  // In production, use a proper markdown parser
  return text
    .replace(/^### (.*$)/gm, "<h3>$1</h3>")
    .replace(/^## (.*$)/gm, "<h2>$1</h2>")
    .replace(/^# (.*$)/gm, "<h1>$1</h1>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
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

export function renderNotebook(notebookJson: unknown): string {
  try {
    const notebook = nb.parse(notebookJson);
    const rendered = notebook.render(dom.window.document);
    // Sanitize HTML to prevent XSS attacks
    const purify = DOMPurify(dom.window);
    return purify.sanitize(rendered.outerHTML);
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
