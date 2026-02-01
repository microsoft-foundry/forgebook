/**
 * Type declarations for notebookjs package
 */
declare module "notebookjs" {
  interface Notebook {
    render(document: Document): HTMLElement;
  }

  interface NotebookJS {
    parse(json: unknown): Notebook;
    markdown: (text: string) => string;
    highlighter: (
      text: string,
      pre: HTMLPreElement,
      code: HTMLElement,
      lang: string
    ) => string;
  }

  const nb: NotebookJS;
  export default nb;
}
