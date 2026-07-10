/**
 * M7-3: 테스트 모드 variant 셀렉터
 *
 * A / B-frontier / B-exaone를 선택하면 스토어(testVariant)에 저장되고,
 * useStreamingChat가 /chat/stream 요청의 variant·model_spec에 실어 보낸다.
 * (프로덕션 기본은 A. B-exaone는 느리고 RunPod 파드가 필요.)
 */
import { useChatStore } from '@/features/chat/chat.store';
import type { TestVariant } from '@/shared/types';

const OPTIONS: { value: TestVariant; label: string }[] = [
  { value: 'A', label: 'A · MAS (기본)' },
  { value: 'B-frontier', label: 'B · gpt-4o-mini' },
  { value: 'B-exaone', label: 'B · EXAONE 4.5' },
];

interface VariantSelectorProps {
  className?: string;
}

export function VariantSelector({ className = '' }: VariantSelectorProps) {
  const testVariant = useChatStore((s) => s.testVariant);
  const setTestVariant = useChatStore((s) => s.setTestVariant);

  return (
    <div className={`flex items-center gap-2 text-xs ${className}`}>
      <label htmlFor="variant-select" className="whitespace-nowrap opacity-80">
        테스트 모델
      </label>
      <select
        id="variant-select"
        value={testVariant}
        onChange={(e) => setTestVariant(e.target.value as TestVariant)}
        className="rounded-md border border-white/30 bg-white/10 px-2 py-1 text-white focus:outline-none"
      >
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value} className="text-dark-navy">
            {o.label}
          </option>
        ))}
      </select>
      {testVariant === 'B-exaone' && (
        <span
          className="text-amber-200"
          title="EXAONE는 추론 모델이라 응답이 수십 초~2분+ 걸리고 RunPod 파드가 켜져 있어야 합니다."
        >
          ⚠ 느림·파드
        </span>
      )}
    </div>
  );
}
