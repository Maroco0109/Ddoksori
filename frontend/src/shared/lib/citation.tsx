/**
 * Citation Utilities - Sprint 1 S1-4
 * Extract and render inline citations [1], [2], [3] from backend answers
 */

import React from 'react';
import type { Citation, SourceMetadata } from '@/shared/types';

/**
 * Extract inline citations [1], [2], [3] from answer text
 * Match them to sources array from backend response
 *
 * @param answerText - Full answer text with inline citations [N]
 * @param sources - Array of source metadata from backend
 * @returns Array of unique citations with source metadata
 *
 * @example
 * const citations = extractCitations(
 *   "소비자24에 따르면 [1] 이러한 경우 [2]...",
 *   [source1, source2, source3]
 * );
 * // Returns: [{ id: 1, sourceIndex: 0, source: source1 }, ...]
 */
export function extractCitations(
  answerText: string,
  sources: SourceMetadata[]
): Citation[] {
  const citationRegex = /\[(\d+)\]/g;
  const citations: Citation[] = [];
  const matches = answerText.matchAll(citationRegex);

  for (const match of matches) {
    const citationNum = parseInt(match[1], 10);
    const sourceIndex = citationNum - 1; // [1] maps to index 0

    if (sourceIndex >= 0 && sourceIndex < sources.length) {
      citations.push({
        id: citationNum,
        sourceIndex,
        source: sources[sourceIndex],
      });
    }
  }

  // Return unique citations (deduplicate by id)
  const uniqueCitations = Array.from(
    new Map(citations.map((c) => [c.id, c])).values()
  );

  return uniqueCitations;
}

/**
 * Render answer text with clickable inline citation footnotes
 * Splits text by [N] patterns and makes them interactive buttons
 *
 * @param text - Answer text with inline citations
 * @param onCitationClick - Callback when citation is clicked
 * @returns Array of React nodes (text + citation buttons)
 *
 * @example
 * <div>
 *   {renderTextWithCitations(answer, (citationId) => {
 *     setCitationModal(citationId);
 *   })}
 * </div>
 */
export function renderTextWithCitations(
  text: string,
  onCitationClick: (citationId: number) => void
): React.ReactNode[] {
  // Split text by citation pattern [N]
  const parts = text.split(/(\[\d+\])/g);

  return parts.map((part, index) => {
    const match = part.match(/\[(\d+)\]/);

    if (match) {
      const citationId = parseInt(match[1], 10);
      return (
        <button
          key={index}
          type="button"
          onClick={() => onCitationClick(citationId)}
          className="inline-flex items-center justify-center text-xs font-semibold text-deep-teal hover:text-mint-green hover:underline transition-colors cursor-pointer mx-0.5"
          aria-label={`참고 자료 ${citationId} 보기`}
        >
          {part}
        </button>
      );
    }

    // Regular text - preserve line breaks
    return <span key={index}>{part}</span>;
  });
}

/**
 * Check if text contains any citations
 * @param text - Text to check
 * @returns true if text contains [N] patterns
 */
export function hasCitations(text: string): boolean {
  return /\[\d+\]/.test(text);
}

/**
 * Count total citations in text
 * @param text - Text to analyze
 * @returns Number of citation references found
 */
export function countCitations(text: string): number {
  const matches = text.matchAll(/\[\d+\]/g);
  return Array.from(matches).length;
}
