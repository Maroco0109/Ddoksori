import { useState } from 'react';
import { AlertTriangle, ExternalLink } from 'lucide-react';
import type { MessageWithCitations } from '@/shared/types';
import { MarkdownRenderer } from '@/shared/components/MarkdownRenderer';
import { CitationModal } from './CitationModal';
import { FollowupChips } from './FollowupChips';

interface MessageBubbleProps {
  message: MessageWithCitations;
  chatType?: 'dispute' | 'general';
  onFollowupSelect?: (question: string) => void;
}

export function MessageBubble({
  message,
  chatType = 'dispute',
  onFollowupSelect,
}: MessageBubbleProps) {
  const [selectedCitationId, setSelectedCitationId] = useState<number | null>(
    null
  );

  const isAI = message.type === 'ai';
  const isRestricted = message.isRestricted;

  const selectedCitation = selectedCitationId
    ? message.citations?.find((c) => c.id === selectedCitationId)
    : null;

  const userBgColor = chatType === 'dispute' ? 'bg-deep-teal' : 'bg-mint-green';

  if (isAI && isRestricted && message.agencyInfo) {
    return (
      <div className="mb-4 md:mb-6 flex flex-col items-start">
        <div className="max-w-[90%] sm:max-w-[85%] md:max-w-[80%] rounded-2xl overflow-hidden border-2 border-amber-400 shadow-lg">
          <div className="bg-amber-50 px-4 py-3 border-b border-amber-200 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            <span className="font-semibold text-amber-800">
              전문가 상담이 필요한 영역입니다
            </span>
          </div>
          
          <div className="bg-white px-4 sm:px-6 py-4">
            <div className="mb-4 p-3 bg-amber-50 rounded-lg">
              <p className="font-medium text-dark-navy mb-1">
                {message.agencyInfo.full_name}
              </p>
              <p className="text-sm text-gray-600">
                {message.agencyInfo.description}
              </p>
              <a
                href={message.agencyInfo.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-sm text-deep-teal hover:underline"
              >
                <ExternalLink className="w-4 h-4" />
                공식 웹사이트 방문
              </a>
            </div>
            
            <div className="prose prose-sm max-w-none">
              <MarkdownRenderer
                content={message.content}
                onCitationClick={setSelectedCitationId}
              />
            </div>
            
            {message.agencyInfo.restriction_reason && (
              <div className="mt-4 p-3 bg-gray-100 rounded-lg text-sm text-gray-700">
                <strong>안내:</strong> {message.agencyInfo.restriction_reason}
              </div>
            )}
          </div>
        </div>
        
        <div className="text-xs text-gray-purple mt-1 md:mt-2 px-2">
          {message.timestamp.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        className={`mb-4 md:mb-6 flex flex-col ${
          isAI ? 'items-start' : 'items-end'
        }`}
      >
        <div
          className={`max-w-[85%] sm:max-w-[75%] md:max-w-[70%] px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl leading-relaxed text-sm sm:text-base ${
            isAI
              ? 'bg-lavender/30 text-dark-navy rounded-bl-sm'
              : `${userBgColor} text-white rounded-br-sm whitespace-pre-line`
          }`}
        >
          {isAI ? (
            <>
              <MarkdownRenderer
                content={message.content}
                onCitationClick={setSelectedCitationId}
              />
              {message.followupQuestions &&
                message.followupQuestions.length > 0 &&
                onFollowupSelect && (
                  <FollowupChips
                    questions={message.followupQuestions}
                    onSelect={onFollowupSelect}
                  />
                )}
            </>
          ) : (
            message.content
          )}
        </div>

        <div className="text-xs text-gray-purple mt-1 md:mt-2 px-2">
          {message.timestamp.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>

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
