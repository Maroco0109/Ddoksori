# Moderation Fallback 정책

Sprint 1에서 정의된 입력 Guardrail 정책입니다.

## 개요

OpenAI Moderation API (`omni-moderation-latest`)를 사용하여 사용자 입력을 검사합니다.
출력 Moderation은 Sprint 4 (Fast Path)에서 추가 예정입니다.

## 차단 카테고리

| 카테고리 | 동작 | 설명 |
|----------|------|------|
| `hate` | 차단 | 혐오 표현 |
| `hate/threatening` | 차단 | 위협적 혐오 표현 |
| `harassment/threatening` | 차단 | 위협적 괴롭힘 |
| `self-harm` | 차단 | 자해 관련 |
| `self-harm/intent` | 차단 | 자해 의도 |
| `self-harm/instructions` | 차단 | 자해 방법 안내 |
| `sexual/minors` | 차단 | 미성년자 관련 성적 콘텐츠 |
| `violence/graphic` | 차단 | 극단적 폭력 묘사 |
| `harassment` | 경고 | 일반 괴롭힘 (경고만) |
| `sexual` | 경고 | 성적 콘텐츠 (경고만) |
| `violence` | 경고 | 폭력 (경고만) |

## Fallback 동작

### 1. 차단 (Blocked)

사용자 입력이 차단 카테고리에 해당하는 경우:

```
요청하신 내용은 서비스 정책상 처리할 수 없습니다. 
소비자 분쟁 관련 질문을 입력해 주세요.
```

- 로그: `WARNING` 레벨로 차단된 카테고리 기록
- 처리: 파이프라인 진행 중단, fallback 메시지 반환

### 2. API 오류 (Error)

Moderation API 호출 실패 시:

```
일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.
```

- 기본 동작: **Fail-open** (오류 시 처리 계속)
- 로그: `ERROR` 레벨로 오류 기록
- 환경변수 `MODERATION_FAIL_OPEN=false`로 fail-close 전환 가능

### 3. 타임아웃 (Timeout)

API 응답 지연 (기본 5초) 시:

```
요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.
```

- Fail-open 모드에서는 경고 로그 후 처리 계속
- Fail-close 모드에서는 차단 처리

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_API_KEY` | (필수) | OpenAI API 키 |
| `MODERATION_TIMEOUT` | `5.0` | API 타임아웃 (초) |
| `MODERATION_FAIL_OPEN` | `true` | 오류 시 처리 계속 여부 |

## 사용 예시

```python
from app.guardrail import InputModerator, get_fallback_message

moderator = InputModerator()
result = moderator.check(user_input)

if not result.should_proceed:
    return moderator.get_fallback_response(result)

# 정상 처리 계속
```

## 로깅 정책

- 차단된 입력 내용은 로그에 기록하지 않음 (개인정보 보호)
- 차단 카테고리만 기록: `[Moderation] Input blocked. Categories: ['hate']`
- API 오류 시 상세 에러 메시지 기록

## 향후 계획

- Sprint 4: 출력 Moderation 추가 (Fast Path)
- 한국어 특화 필터 규칙 추가 검토
