/**
 * SafetyWarning Component - Sprint 1 S1-4
 * Displays amber warning box with clarifying questions when evidence is insufficient
 */

interface SafetyWarningProps {
  questions: string[];
}

/**
 * Safety warning message displayed as separate AI message
 * Shown when backend returns has_sufficient_evidence=false
 *
 * @param questions - List of clarifying questions from backend
 */
export function SafetyWarning({ questions }: SafetyWarningProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <div className="mb-4 md:mb-6 flex flex-col items-start">
      <div className="max-w-[85%] sm:max-w-[75%] md:max-w-[70%] px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl leading-relaxed text-sm sm:text-base bg-amber-50 border-2 border-amber-300 text-dark-navy rounded-bl-sm shadow-md">
        {/* Warning Header */}
        <div className="flex items-start mb-3">
          <span className="text-2xl mr-2" role="img" aria-label="warning">
            ⚠️
          </span>
          <p className="font-semibold text-base">추가 정보가 필요합니다</p>
        </div>

        {/* Explanation */}
        <p className="mb-3">
          정확한 안내를 위해 다음 정보를 추가로 알려주시면 도움이 될 것 같습니다:
        </p>

        {/* Questions List */}
        <ul className="list-disc list-inside space-y-2 pl-2">
          {questions.map((question, index) => (
            <li key={index} className="text-sm sm:text-base">
              {question}
            </li>
          ))}
        </ul>

        {/* Helpful Tip */}
        <div className="mt-4 pt-3 border-t border-amber-200">
          <p className="text-xs sm:text-sm text-gray-600">
            💡 위 질문에 답변해 주시면 더 정확한 기관 추천과 유사 사례를 제공해 드릴 수
            있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
