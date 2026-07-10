# M7-3 프론트 variant 셀렉터 (계획 + 결과)

- 작성일: 2026-07-05
- 모듈: `M7-3` 프론트 variant 셀렉터
- 상위: 로드맵 §M7, 선행 M7-1(계측)·M7-2(라우팅)
- 성격: **프론트엔드.** 백엔드는 M7-2에서 완료(variant/model_spec 수신).

## 0. 한 줄 요약

프론트에서 **A / B-frontier / B-exaone**를 골라 `/chat/stream` 요청의 `variant`·`model_spec`에 실어 보내는 테스트 모드 셀렉터를 추가했다. 선택은 스토어(`testVariant`)에 저장되고 `useStreamingChat`이 모든 전송 호출에 공통 주입한다(3개 호출부 수정 불필요).

## 1. 변경

- **타입**(`shared/types/chat.types.ts`): `ChatAPIRequest`에 `variant?: 'A'|'B'`, `model_spec?: 'frontier'|'exaone'` 추가. `TestVariant`(`'A'|'B-frontier'|'B-exaone'`) + `testVariantToRequest()` 매핑 헬퍼.
- **스토어**(`chat.store.ts`): `testVariant: TestVariant`(기본 `'A'`) + `setTestVariant`.
- **훅**(`useStreamingChat.ts`): `enhancedRequest`에 `...testVariantToRequest(store.testVariant)` 주입 → **모든 startStream 호출(분쟁 제출/후속/일반)이 자동 반영**.
- **컴포넌트**(`components/VariantSelector.tsx`): `<select>` 3택 + B-exaone일 때 "⚠ 느림·파드" 경고.
- **렌더**(`ChatPage.tsx`): 분쟁 상담 헤더(deep-teal 바)에 `<VariantSelector />` 배치(전역 스토어라 한 곳 배치로 충분).

## 2. 설계 노트

- **DRY 주입**: 3개 요청 빌드 사이트를 각각 고치지 않고 `useStreamingChat` 한 곳에서 스토어값을 주입. 미선택(A) 시 `variant:'A'`만 실려 백엔드 기본과 동일.
- **model_spec 승격 활용**(M7-2): B-frontier→`{variant:B, model_spec:frontier}`, B-exaone→`{variant:B, model_spec:exaone}`.
- **B-exaone 경고**: 추론 모델 지연(수십 초~2분+)·RunPod 파드 필요를 UI에 명시.
- **프로덕션 기본 A**: 기본값 A라 일반 사용 흐름 불변, 셀렉터는 테스트/비교용.

## 3. 스코프 경계

- **대상**: 타입·스토어·훅 주입·셀렉터 컴포넌트·헤더 렌더.
- **비대상**: LangSmith(M7-4), B 토큰 스트리밍, mainline 확정. 기존 SSE/메시지 렌더 로직 변경 없음.

## 4. 완료 기준 / 검증

- [x] `ChatAPIRequest`에 variant/model_spec, 셀렉터→스토어→요청 주입 경로 구성.
- [x] B-exaone 경고 표기.
- [x] 빌드 통과: 컨테이너에서 `vite build` 성공(2790 modules, 에러 없음). 신규 파일 타입 이슈 없음(기존 tsc 부채는 무관, 프로젝트는 vite build 게이트).
- [x] **실제 브라우저 QA(gstack /browse)**: 아래 §5.

## 5. 결과

- 5파일 변경(타입/스토어/훅/컴포넌트/ChatPage). `vite build` 성공.
- 흐름: 셀렉터 선택 → `store.testVariant` → `useStreamingChat` 주입 → `/chat/stream` body(`variant`/`model_spec`) → 백엔드 라우팅(M7-2 검증).

### 5.1 브라우저 QA (2026-07-05, 실제 브라우저)

frontend를 m7-3 worktree로 띄우고(:5173) + backend(:8000), gstack `/browse`로 `/chat` 검증:

1. **셀렉터 렌더**: 분쟁 상담 헤더에 `테스트 모델` combobox + 3 옵션(`A · MAS (기본)`[기본 선택]/`B · gpt-4o-mini`/`B · EXAONE 4.5`). 콘솔 에러 없음.
2. **B-exaone 경고**: `B · EXAONE 4.5` 선택 시 `⚠ 느림·파드` 표시, 다른 옵션 선택 시 사라짐.
3. **end-to-end 전송**: `B · gpt-4o-mini` 선택 후 일반 상담 입력 전송 → `POST /chat/stream 200` → DB `workflow_runs` 최신 general run이 **`variant='B'`**로 적재됨(`B|general|온라인으로 구매한 신발의 환불에 대한…`). 프론트 셀렉터→스토어→요청→백엔드 라우팅 전 구간 실증.

## 6. Next gate → M7-4

LangSmith 리치 트레이싱(보완): variant/session 태그 표준화, (선택) dataset/eval. 자체 스택 canonical 유지.
