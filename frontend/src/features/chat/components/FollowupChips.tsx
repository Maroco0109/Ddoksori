interface FollowupChipsProps {
  questions: string[];
  onSelect: (question: string) => void;
}

export function FollowupChips({ questions, onSelect }: FollowupChipsProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-200/50">
      {questions.slice(0, 3).map((question) => (
        <button
          key={question}
          onClick={() => onSelect(question)}
          className="
            px-3 py-1.5 text-sm
            bg-lavender/20 hover:bg-lavender/40
            text-deep-teal
            rounded-full
            border border-lavender/50
            transition-colors duration-200
            cursor-pointer
            text-left
          "
        >
          {question}
        </button>
      ))}
    </div>
  );
}
