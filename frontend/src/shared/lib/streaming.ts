/**
 * Client-Side Streaming Utility - Sprint 1 S1-4
 * Simulates word-by-word streaming for better UX without backend SSE complexity
 */

export interface StreamingOptions {
  /**
   * Number of words to emit per chunk
   * @default 2
   */
  wordsPerChunk?: number;

  /**
   * Delay in milliseconds between chunks
   * @default 30
   */
  delayMs?: number;
}

/**
 * Simulates word-by-word streaming of a complete text response
 * Provides smooth UX without requiring backend Server-Sent Events (SSE)
 *
 * @param text - Complete text to stream
 * @param onChunk - Callback called with each chunk of text
 * @param options - Streaming configuration options
 *
 * @example
 * let streamedText = '';
 * await simulateStreaming(
 *   fullResponse,
 *   (chunk) => {
 *     streamedText += chunk;
 *     setMessage({ ...msg, content: streamedText });
 *   },
 *   { wordsPerChunk: 3, delayMs: 40 }
 * );
 */
export async function simulateStreaming(
  text: string,
  onChunk: (chunk: string) => void,
  options: StreamingOptions = {}
): Promise<void> {
  const { wordsPerChunk = 2, delayMs = 30 } = options;

  // Split text into words while preserving whitespace
  const words = text.split(' ');
  let currentIndex = 0;

  while (currentIndex < words.length) {
    // Get next chunk of words
    const chunkWords = words.slice(currentIndex, currentIndex + wordsPerChunk);
    const chunk = chunkWords.join(' ');

    // Add space after chunk unless it's the last chunk
    const isLastChunk = currentIndex + wordsPerChunk >= words.length;
    onChunk(chunk + (isLastChunk ? '' : ' '));

    currentIndex += wordsPerChunk;

    // Delay before next chunk (skip delay after last chunk)
    if (!isLastChunk) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
}

/**
 * Calculate estimated streaming duration
 * Useful for UI feedback or timeout calculations
 *
 * @param text - Text to stream
 * @param options - Streaming options
 * @returns Estimated duration in milliseconds
 */
export function estimateStreamingDuration(
  text: string,
  options: StreamingOptions = {}
): number {
  const { wordsPerChunk = 2, delayMs = 30 } = options;
  const wordCount = text.split(' ').length;
  const chunkCount = Math.ceil(wordCount / wordsPerChunk);
  return (chunkCount - 1) * delayMs; // -1 because no delay after last chunk
}
