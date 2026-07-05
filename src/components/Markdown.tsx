import { useMemo } from "react";
import { marked } from "marked";

interface MarkdownProps {
  content: string;
}

// Configure marked options if needed
marked.setOptions({
  gfm: true,
  breaks: true,
});

export function Markdown({ content }: MarkdownProps) {
  const html = useMemo(() => {
    try {
      // Parse markdown to HTML (marked.parse returns a string or Promise, but sync is default)
      const rawHtml = marked.parse(content) as string;
      return rawHtml;
    } catch (e) {
      console.error("Markdown parse error:", e);
      return content;
    }
  }, [content]);

  return (
    <div
      className="markdown-body"
      dangerouslySetInnerHTML={{ __html: html }}
      style={{
        lineHeight: "1.6",
        wordBreak: "break-word",
      }}
    />
  );
}
