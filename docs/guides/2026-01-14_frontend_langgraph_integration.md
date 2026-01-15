# 2026-01-14 Frontend LangGraph Integration (PR4)

## 변경사항 요약

- **Frontend-Backend 세션 통합**: LangGraph 오케스트레이터의 멀티턴 세션 지원
- **온보딩 데이터 연동**: 분쟁 상담 폼 데이터를 백엔드 API로 전달
- **타입 시스템 확장**: ChatAPIRequest/Response에 세션 및 온보딩 필드 추가

---

## 1. 구현 배경

PR1-PR3에서 LangGraph 기반 오케스트레이터가 백엔드에 구현되었습니다:
- `/chat` 엔드포인트가 `session_id`, `chat_type`, `onboarding` 파라미터 지원
- 응답에 `session_id` 반환 (멀티턴 대화 추적용)

PR4는 이러한 백엔드 변경사항을 프론트엔드에서 활용하도록 연동합니다.

---

## 2. 구현 내용

### 2.1 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend → Backend 흐름                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. 사용자가 온보딩 폼 작성                                           │
│     └── DisputeFormData (camelCase) → store에 저장                  │
│                                                                     │
│  2. 첫 메시지 전송                                                   │
│     └── ChatAPIRequest {                                            │
│           message: "...",                                           │
│           chat_type: "dispute" | "general",                         │
│           onboarding: OnboardingAPIData (snake_case),               │
│           session_id: undefined (첫 요청)                            │
│         }                                                           │
│                                                                     │
│  3. 백엔드 응답 수신                                                  │
│     └── ChatAPIResponse {                                           │
│           session_id: "uuid-...",  ← 저장                           │
│           answer: "...",                                            │
│           sources: [...]                                            │
│         }                                                           │
│                                                                     │
│  4. 후속 메시지 전송                                                  │
│     └── ChatAPIRequest {                                            │
│           message: "...",                                           │
│           session_id: "uuid-...",  ← 재사용                         │
│           ...                                                       │
│         }                                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 camelCase ↔ snake_case 변환

| Frontend (camelCase) | Backend (snake_case) |
|---------------------|---------------------|
| purchaseDate | purchase_date |
| purchasePlace | purchase_place |
| purchasePlatform | purchase_platform |
| purchaseItem | purchase_item |
| purchaseAmount | purchase_amount |
| disputeDetails | dispute_details |

---

## 3. 수정된 파일

### 3.1 `frontend/src/shared/types/chat.types.ts`

```typescript
// 신규: 백엔드 API용 온보딩 데이터 (snake_case)
export interface OnboardingAPIData {
  purchase_date?: string;
  purchase_place?: string;
  purchase_platform?: string;
  purchase_item?: string;
  purchase_amount?: string;
  dispute_details?: string;
}

// 확장: ChatAPIRequest
export interface ChatAPIRequest {
  message: string;
  session_id?: string;           // 신규
  chat_type?: 'dispute' | 'general';  // 신규
  onboarding?: OnboardingAPIData;     // 신규
  top_k?: number;
  chunk_types?: string[];
  agencies?: string[];
}

// 확장: ChatAPIResponse
export interface ChatAPIResponse {
  session_id: string;            // 신규 (필수)
  answer: string;
  // ...
}
```

### 3.2 `frontend/src/features/chat/chat.store.ts`

```typescript
interface ChatState {
  // 기존 상태...
  
  // 신규 상태
  backendSessionId: string | null;      // 백엔드 세션 ID
  disputeFormData: DisputeFormData | null;  // 온보딩 폼 데이터

  // 신규 액션
  setBackendSessionId: (id: string | null) => void;
  setDisputeFormData: (data: DisputeFormData | null) => void;
}

// startNewChat()에서 신규 상태 리셋
startNewChat: () => {
  set({
    // 기존...
    backendSessionId: null,
    disputeFormData: null,
  });
},
```

### 3.3 `frontend/src/features/chat/hooks/useChatMutation.ts`

```typescript
function convertDisputeFormToOnboarding(): OnboardingAPIData | undefined {
  const disputeFormData = useChatStore.getState().disputeFormData;
  if (!disputeFormData) return undefined;
  
  return {
    purchase_date: disputeFormData.purchaseDate || undefined,
    purchase_place: disputeFormData.purchasePlace || undefined,
    // ...
  };
}

export function useChatMutation() {
  const setBackendSessionId = useChatStore((state) => state.setBackendSessionId);

  return useMutation<ChatAPIResponse, Error, ChatAPIRequest>({
    mutationFn: async (request: ChatAPIRequest) => {
      const backendSessionId = useChatStore.getState().backendSessionId;
      const onboarding = convertDisputeFormToOnboarding();
      
      const enhancedRequest: ChatAPIRequest = {
        ...request,
        session_id: backendSessionId || undefined,
        chat_type: request.chat_type || 'dispute',
        onboarding: onboarding,
      };
      
      return chatService.sendMessage(enhancedRequest);
    },
    onSuccess: (response) => {
      setBackendSessionId(response.session_id);  // 세션 ID 저장
    },
  });
}
```

### 3.4 `frontend/src/features/chat/ChatPage.tsx`

```typescript
// 폼 제출 시 disputeFormData 저장
const handleDisputeFormSubmit = async (event: FormEvent) => {
  // ...
  const formDataForBackend: DisputeFormData = {
    purchaseDate: disputeForm.purchaseDate,
    purchasePlace: disputeForm.purchasePlace,
    purchasePlatform: disputeForm.platform,
    purchaseItem: disputeForm.purchaseItem,
    purchaseAmount: disputeForm.purchaseAmount.replace(/,/g, ''),
    disputeDetails: disputeForm.disputeDetail,
  };
  setDisputeFormData(formDataForBackend);
  // ...
};

// API 호출 시 chat_type 명시
const response = await chatMutation.mutateAsync({
  message: formMessage.content,
  chat_type: 'dispute',  // 또는 'general'
  top_k: 5,
});

// 새 채팅 시작 시 리셋
setBackendSessionId(null);
setDisputeFormData(null);
```

---

## 4. 테스트 시나리오

### 4.1 멀티턴 세션 유지

1. 분쟁 상담 온보딩 폼 작성 → 제출
2. 첫 메시지 전송 → 응답의 `session_id` 저장 확인
3. 두 번째 메시지 전송 → 요청에 동일한 `session_id` 포함 확인
4. 백엔드에서 이전 대화 컨텍스트 유지 확인

### 4.2 새 채팅 시작

1. 사이드바에서 "새 채팅" 클릭
2. `backendSessionId`가 `null`로 리셋 확인
3. `disputeFormData`가 `null`로 리셋 확인
4. 다음 메시지는 새 세션으로 시작

### 4.3 일반 상담

1. 일반 상담 섹션에서 메시지 전송
2. `chat_type: 'general'` 전송 확인
3. 온보딩 데이터 없이 요청 전송 확인

---

## 5. 빌드 검증

```bash
# TypeScript 컴파일 + 번들링
cd frontend && npm run build
# ✓ built in 5.05s

# ESLint 검사
npm run lint
# (에러 없음)
```

---

## 6. 관련 PR

| PR | 내용 | 상태 |
|----|------|------|
| PR1 | State Schema + Checkpointer Factory | 완료 |
| PR2 | 5 Node Functions | 완료 |
| PR3 | StateGraph + `/chat` Endpoint Integration | 완료 |
| **PR4** | **Frontend Integration** | 완료 |

---

## 7. 다음 단계

- S2-5: 기관별 절차/양식 기반 가이드 생성
- S2-6: Backend 서버화 및 배포 (AWS EC2)
