/**
 * PR-5: Status Indicator Component
 * Real-time progress display for SSE streaming
 */

import React from 'react';
import type { StreamingState } from '@/shared/types';

interface StatusIndicatorProps {
  streamingState: StreamingState;
  className?: string;
}

/**
 * Displays real-time streaming progress with status text and progress bar
 *
 * @example
 * <StatusIndicator streamingState={streamingState} />
 */
export function StatusIndicator({ streamingState, className = '' }: StatusIndicatorProps) {
  const { isStreaming, status, progress, error } = streamingState;

  // Don't render if not streaming and no error
  if (!isStreaming && !error) {
    return null;
  }

  // Error state
  if (error) {
    return (
      <div className={`flex items-center gap-2 text-red-500 text-sm ${className}`}>
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className={`space-y-2 ${className}`}>
      {/* Status text with loading spinner */}
      <div className="flex items-center gap-2 text-sm text-gray-600">
        {/* Loading spinner */}
        <svg
          className="w-4 h-4 animate-spin text-blue-500"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        <span className="font-medium">{status}</span>
        <span className="text-gray-400">({progress}%)</span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-400 to-blue-600 transition-all duration-300 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Compact version of StatusIndicator for inline display
 */
export function StatusIndicatorCompact({ streamingState, className = '' }: StatusIndicatorProps) {
  const { isStreaming, status, progress, error } = streamingState;

  if (!isStreaming && !error) {
    return null;
  }

  if (error) {
    return (
      <span className={`text-red-500 text-xs ${className}`}>
        {error}
      </span>
    );
  }

  return (
    <div className={`inline-flex items-center gap-1.5 ${className}`}>
      {/* Small spinner */}
      <svg
        className="w-3 h-3 animate-spin text-blue-500"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <span className="text-xs text-gray-500">{status}</span>

      {/* Mini progress bar */}
      <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

export default StatusIndicator;
