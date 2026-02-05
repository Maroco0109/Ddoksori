interface FollowupChipsProps {
  questions: string[];
}

export function FollowupChips({ questions }: FollowupChipsProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-200/50">
      {questions.slice(0, 3).map((question) => (
        <span
          key={question}
          className="
            px-3 py-1.5 text-sm
            bg-lavender/20
            text-deep-teal
            rounded-full
            border border-lavender/50
            select-none
          "
        >
          {question}
        </span>
      ))}
    </div>
  );
}
