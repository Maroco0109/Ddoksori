# M4-A4 러너 최소 구현 (결과)

- 작성일: 2026-07-05
- 모듈: `M4-A4` 러너 최소 구현
- 상위: `M4-A` 챗봇/LLM 보안. 데이터: `security_eval_v1.jsonl`(A1~A3, 26건)
- 성격: **실행 러너 재사용(최소 확장).** 새 실행 경로 없이 기존 `/chat` 재사용. 스코어러/build는 A5.

## 0. 한 줄 요약

`run_answer_eval.py`(M5-5 러너)를 **보안 goldenset 구동 가능하도록 최소 확장**했다. 추가 인자는 `--session-prefix`(캠페인 네임스페이스: `m5-5`=품질 / `m4a`=보안), `--limit`(N건만), `--dry-run`(인프라 없이 요청 검증)뿐이며 **M5 기존 동작은 기본값으로 불변**이다. dry-run으로 보안셋 A/B 구동을 검증했고, **라이브 1케이스 적재는 로컬 인프라(DB/백엔드) 미가동으로 보류**한다.

## 1. 범위

- **목표**: 보안셋을 A/B `/chat`로 실행·적재하는 러너 확보(최소). 1케이스로 검증.
- **비목표**: 스코어러·build(A5), OWASP coverage(A6), 방어 강화. 스키마/DB/가드레일 로직 변경 없음.
- **재사용 원칙**: `/chat`가 트리거하는 기존 M5-1/M3 적재(`workflow_runs.answer` + `retrieval_events`)를 그대로 사용. 새 실행 경로 없음.

## 2. 변경 (backend/scripts/evaluation/run_answer_eval.py)

| 추가 인자 | 의미 | 기본값(=M5 불변) |
| --- | --- | --- |
| `--session-prefix` | `session_id`의 캠페인 네임스페이스. `m5-5`=품질, `m4a`=보안 | `m5-5` |
| `--limit N` | 앞에서 N건만 실행(스모크용) | 전체 |
| `--dry-run` | POST 없이 요청 body·session_id 출력(인프라 불필요) | off |

- `session_id = <prefix>-<label>-<id>`로 일반화(기존 하드코딩 `m5-5-` 제거).
- 보안 러너 규약: `--session-prefix m4a`로 DB에서 보안 run을 품질 run과 분리(다운스트림 A5 스코어러가 `m4a-<label>-<id>` 파싱).
- **variant B 주의**: 백엔드 `VARIANT_B_MODEL_SPEC`(frontier|exaone)에 따라 모델 결정. `exaone`은 EXAONE 파드/터널 필요(추론 모델; 근거 `docs/report/2026-07-05-reasoning-vs-nonreasoning-exaone.md`).

## 3. 검증 (실행 증거)

### 3.1 dry-run (인프라 불필요) — PASS
- `py_compile` OK.
- **M5 back-compat**: 기본 실행 시 `session_id=m5-5-A-law-001`(prefix 불변) 확인.
- **보안셋 variant A**: `--eval-set security_eval_v1.jsonl --session-prefix m4a --variant A --label A --limit 1`
  → `session_id=m4a-A-sec-inj-001`, body에 보안 케이스 `query` 정확히 실림.
- **보안셋 variant B**: 동일 조건 `--variant B --label Bexaone`
  → `session_id=m4a-Bexaone-sec-inj-001`, `variant=B`.

재현:
```bash
python backend/scripts/evaluation/run_answer_eval.py \
  --eval-set backend/data/golden_set/security_eval_v1.jsonl \
  --session-prefix m4a --variant A --label A --limit 1 --dry-run
```

### 3.2 라이브 1케이스 A/B 적재 — 보류(인프라 미가동)
2026-07-05 로컬 인프라 상태: DB(5433) closed, 백엔드(8000) closed, EXAONE 터널(19080) closed, Docker 미가용(WSL 통합 off). 라이브 실행은 아래 선행 조건 충족 후 가능:

- **필수**: 로컬 pgvector DB + 임베딩 서버 + 백엔드(`:8000`) 기동, `OPENAI_API_KEY` 등.
- **variant A**: MAS 파이프라인 모델.
- **variant B**: `VARIANT_B_MODEL_SPEC=frontier`(파드 불필요) 또는 `=exaone`(RunPod 파드+터널 필요, 비용 발생).

라이브 실행 커맨드(인프라 기동 후):
```bash
# variant A
python backend/scripts/evaluation/run_answer_eval.py \
  --eval-set backend/data/golden_set/security_eval_v1.jsonl \
  --session-prefix m4a --variant A --label A --limit 1
# variant B (frontier: 파드 불필요) — 백엔드에 VARIANT_B_MODEL_SPEC=frontier 설정 후
python backend/scripts/evaluation/run_answer_eval.py \
  --eval-set backend/data/golden_set/security_eval_v1.jsonl \
  --session-prefix m4a --variant B --label Bfrontier --limit 1
```
적재 확인: `workflow_runs`에서 `session_id LIKE 'm4a-%'` 조회로 answer/variant/blocked 확인.

## 4. 완료 상태

- [x] 러너가 보안 goldenset을 A/B로 구동하도록 최소 확장(코드).
- [x] dry-run으로 보안셋 A/B 요청·session 네임스페이스 검증, M5 back-compat 확인.
- [ ] **라이브 1케이스 A/B 적재** — 인프라(DB/백엔드, B-exaone는 파드) 기동 후 실행. 커맨드는 §3.2.

## 5. Next gate → M4-A5

batch 실행 + 보안 스코어러: `m4a-` run들을 DB에서 join해 block/refuse/no_leak 채점(`build` + `score_security_eval.py`), 전체 pass/fail summary(A/B) + `security_eval_scores.json`. A4의 라이브 적재는 A5 실행 시 함께 수행 가능.
