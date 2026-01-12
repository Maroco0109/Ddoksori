/**
 * MessageBubble Component - Sprint 1 S1-4
 * Renders chat messages with inline citation support
 */

import React, { useState } from 'react';
import type { MessageWithCitations } from '@/shared/types';
import { renderTextWithCitations } from '@/shared/lib/citation';
import { CitationModal } from './CitationModal';

interface MessageBubbleProps {
  message: MessageWithCitations;
  chatType?: 'dispute' | 'general';
}

/**
 * Chat message bubble with support for:
 * - AI vs User styling
 * - Inline clickable citations [1], [2], [3]
 * - Citation modal on click
 * - Different colors per chat type
 *
 * @param message - Message with optional citations
 * @param chatType - Chat type for styling (dispute = teal, general = mint-green)
 */
export function MessageBubble({
  message,
  chatType = 'dispute',
}: MessageBubbleProps) {
  const [selectedCitationId, setSelectedCitationId] = useState<number | null>(
    null
  );

  const isAI = message.type === 'ai';

  // Find selected citation metadata
  const selectedCitation = selectedCitationId
    ? message.citations?.find((c) => c.id === selectedCitationId)
    : null;

  // User message background color varies by chat type
  const userBgColor = chatType === 'dispute' ? 'bg-deep-teal' : 'bg-mint-green';

  return (
    <>
      <div
        className={`mb-4 md:mb-6 flex flex-col ${
          isAI ? 'items-start' : 'items-end'
        }`}
      >
        {/* Message Bubble */}
        <div
          className={`max-w-[85%] sm:max-w-[75%] md:max-w-[70%] px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl leading-relaxed text-sm sm:text-base whitespace-pre-line ${
            isAI
              ? 'bg-lavender/30 text-dark-navy rounded-bl-sm'
              : `${userBgColor} text-white rounded-br-sm`
          }`}
        >
          {/* AI messages with citations render as interactive elements */}
          {isAI && message.citations && message.citations.length > 0
            ? renderTextWithCitations(message.content, setSelectedCitationId)
            : message.content}
        </div>

        {/* Timestamp */}
        <div className="text-xs text-gray-purple mt-1 md:mt-2 px-2">
          {message.timestamp.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>

      {/* Citation Modal */}
      {selectedCitation && (
        <CitationModal
          citation={selectedCitation.source}
          citationNumber={selectedCitation.id}
          onClose={() => setSelectedCitationId(null)}
        />
      )}
    </>
  );
}
