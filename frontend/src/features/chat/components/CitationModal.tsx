/**
 * CitationModal Component - Sprint 1 S1-4
 * Displays full source metadata when citation footnote is clicked
 */

import React from 'react';
import type { SourceMetadata } from '@/shared/types';

interface CitationModalProps {
  citation: SourceMetadata;
  citationNumber: number;
  onClose: () => void;
}

/**
 * Full-screen modal displaying citation source details
 *
 * @param citation - Source metadata from backend
 * @param citationNumber - Citation ID [1], [2], [3]
 * @param onClose - Callback to close modal
 */
export function CitationModal({
  citation,
  citationNumber,
  onClose,
}: CitationModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-deep-teal text-white px-6 py-4 rounded-t-2xl flex items-center justify-between">
          <h3 className="text-lg font-bold">참고 자료 [{citationNumber}]</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-white hover:text-gray-200 text-2xl leading-none transition-colors"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Document Title */}
          <div>
            <p className="text-sm font-semibold text-gray-600">문서 제목</p>
            <p className="text-base text-dark-navy mt-1">{citation.doc_title}</p>
          </div>

          {/* Source Organization */}
          <div>
            <p className="text-sm font-semibold text-gray-600">출처 기관</p>
            <p className="text-base text-dark-navy mt-1">{citation.source_org}</p>
          </div>

          {/* Decision Date (if available) */}
          {citation.decision_date && (
            <div>
              <p className="text-sm font-semibold text-gray-600">결정일</p>
              <p className="text-base text-dark-navy mt-1">
                {citation.decision_date}
              </p>
            </div>
          )}

          {/* Similarity Score */}
          <div>
            <p className="text-sm font-semibold text-gray-600">유사도</p>
            <div className="flex items-center mt-1">
              <div className="flex-1 bg-gray-200 rounded-full h-2 mr-3">
                <div
                  className="bg-deep-teal h-2 rounded-full transition-all"
                  style={{ width: `${citation.similarity * 100}%` }}
                />
              </div>
              <p className="text-base text-dark-navy font-semibold">
                {(citation.similarity * 100).toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Document ID */}
          <div>
            <p className="text-sm font-semibold text-gray-600">문서 ID</p>
            <p className="text-sm text-gray-600 mt-1 font-mono">
              {citation.doc_id}
            </p>
          </div>

          {/* Chunk Type */}
          <div>
            <p className="text-sm font-semibold text-gray-600">청크 유형</p>
            <p className="text-sm text-gray-600 mt-1">{citation.chunk_type}</p>
          </div>

          {/* Chunk ID */}
          <div>
            <p className="text-sm font-semibold text-gray-600">청크 ID</p>
            <p className="text-sm text-gray-600 mt-1 font-mono break-all">
              {citation.chunk_id}
            </p>
          </div>

          {/* Collection Date (if available) */}
          {citation.collected_at && (
            <div>
              <p className="text-sm font-semibold text-gray-600">수집일</p>
              <p className="text-sm text-gray-600 mt-1">
                {citation.collected_at}
              </p>
            </div>
          )}

          {/* Source URL (if available) */}
          {citation.url && (
            <div>
              <p className="text-sm font-semibold text-gray-600">원문 링크</p>
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-deep-teal hover:underline mt-1 block break-all"
              >
                {citation.url}
              </a>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200">
          <button
            type="button"
            onClick={onClose}
            className="w-full bg-deep-teal text-white py-3 rounded-lg font-semibold hover:bg-mint-green transition-all"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
