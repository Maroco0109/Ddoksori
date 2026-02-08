/**
 * MarkdownRenderer Component
 * Renders markdown content with syntax highlighting for code blocks
 * and support for inline citations [1], [2], etc.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface MarkdownRendererProps {
  content: string;
  onCitationClick?: (citationId: number) => void;
}

/**
 * Renders markdown content with:
 * - Syntax highlighted code blocks
 * - Styled inline code
 * - Clickable citation markers [1], [2], [3]
 * - Tailwind-styled typography
 */
export function MarkdownRenderer({
  content,
  onCitationClick,
}: MarkdownRendererProps) {
  // Process citations: replace [1], [2] with placeholder spans
  const processedContent = content.replace(
    /\[(\d+)\]/g,
    (_, num) => `<cite-${num}>`
  );

  return (
    <ReactMarkdown
      components={{
        // Code blocks with syntax highlighting
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || '');
          const codeString = String(children).replace(/\n$/, '');

          // Check if this is a code block (has language) or inline code
          const isCodeBlock = match || codeString.includes('\n');

          if (isCodeBlock) {
            return (
              <SyntaxHighlighter
                style={oneDark}
                language={match?.[1] || 'text'}
                PreTag="div"
                className="rounded-lg my-2 text-sm"
              >
                {codeString}
              </SyntaxHighlighter>
            );
          }

          // Inline code
          return (
            <code
              className="bg-lavender/40 text-dark-navy px-1.5 py-0.5 rounded text-sm font-mono"
              {...props}
            >
              {children}
            </code>
          );
        },
        // Paragraphs - check for citation placeholders
        p({ children }) {
          return <p className="mb-2 last:mb-0">{processCitations(children, onCitationClick)}</p>;
        },
        // Lists
        ul({ children }) {
          return <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>;
        },
        li({ children }) {
          return <li>{processCitations(children, onCitationClick)}</li>;
        },
        // Strong/Bold
        strong({ children }) {
          return <strong className="font-semibold">{children}</strong>;
        },
        // Emphasis/Italic
        em({ children }) {
          return <em className="italic">{children}</em>;
        },
        // Links (마크다운 링크를 클릭 가능한 하이퍼링크로 렌더링)
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-deep-teal hover:text-mint-green underline cursor-pointer"
            >
              {children}
            </a>
          );
        },
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}

/**
 * Process children to find and replace citation placeholders with clickable buttons
 */
function processCitations(
  children: React.ReactNode,
  onCitationClick?: (id: number) => void
): React.ReactNode {
  if (!children) return children;

  // Handle array of children
  if (Array.isArray(children)) {
    return children.map((child, index) => (
      <React.Fragment key={index}>
        {processCitations(child, onCitationClick)}
      </React.Fragment>
    ));
  }

  // Handle string children - look for citation placeholders
  if (typeof children === 'string') {
    const parts = children.split(/(<cite-\d+>)/g);

    if (parts.length === 1) return children;

    return parts.map((part, index) => {
      const citationMatch = part.match(/<cite-(\d+)>/);
      if (citationMatch) {
        const citationId = parseInt(citationMatch[1], 10);
        return (
          <button
            key={index}
            onClick={() => onCitationClick?.(citationId)}
            className="text-xs font-semibold text-deep-teal hover:text-mint-green hover:underline cursor-pointer mx-0.5"
          >
            [{citationId}]
          </button>
        );
      }
      return part;
    });
  }

  return children;
}
