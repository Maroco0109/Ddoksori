## 플랜
| 단계 | 목표/산출물 | 네가 구현할 것 (핵심 작업) | “정해야 하는 것”(필수 결정) | 위임 포인트 | 체크/완료 기준 |
| --- | --- | --- | --- | --- | --- |
| 9 | **변경 최소화(키워드 확장)** | Query Analysis에서 `keywords`에 `onboarding.purchase_item`을 append하여 criteria가 품목 키워드를 받게 함 | 중복/공백 처리 규칙(동일 키워드 재추가 방지) | 안전한 append 로직/중복 제거 코드 | retrieval로 넘어온 keywords에 purchase_item 포함 확인 |
| 10 | **criteria 사전 매핑 + LLM 보정** | criteria 노드에서 keywords 복사본으로 룰 기반 매핑 → 매핑된 키워드는 후보에서 제거 → 매핑 실패 키워드만 LLM 분류 | LLM 프롬프트(분류 불필요 키워드 제외 지시), 분류 대상/제외 규칙 | 프롬프트/파싱/에러 처리 | 매핑 성공/실패 분리 로직 동작 |
| 11 | **카테고리 메타데이터 저장** | 키워드별 (section/category/subcategory) 매핑 결과를 구조화해 보관 | 결과 저장 위치(state? retrieval_task_input?) | 데이터 구조 설계 | 각 키워드의 분류 결과가 누락 없이 저장됨 |
| 12 | **분류 필터 적용 검색** | criteria 검색에서 분류 결과로 메타데이터 필터를 적용한 DB 조회 수행 | 메타데이터 필터 키 명칭/검색 함수 변경 여부 | 검색 호출부 수정 | 분류 기반 필터가 실제 검색에 적용됨 |
| 13 | **다중 세트 병합 TopK** | 매핑 세트가 2개 이상일 때 세트별 검색 → 결과 병합/중복 제거 → 최종 top_k | 병합 기준(유사도/중복 제거 키) | 병합 로직/정렬 | 다중 세트에서도 안정적 top_k 반환 |

---

## 변경 요약 통합표 (2026-02-03 ~ 2026-02-04)

| 파일 | 2026-02-03 변경 내용 | 2026-02-04 변경 내용 |
| --- | --- | --- |
| `backend/app/agents/query_analysis/agent.py` | 온보딩 `purchase_item`을 `keywords`에 추가하여 retrieval에 전달되도록 수정 (v1/v2 모두) | - |
| `backend/app/agents/retrieval/tools/specialized_retrievers.py` | `criteria_search()` 추가(하이브리드 RRF + metadata 필터), 기본 `document_type`를 `시행규칙/별표`로 설정 | `criteria_search()`를 LawRetriever에서 CriteriaRetriever로 이동. 대/중분류 필터 제거, 소분류 부분일치(LIKE)만 적용. `chunk_type IN ('자식_청크','손자_청크')` 필터 추가(BM25/Vector 모두). `rrf_k` 파라미터화. `search_by_category()` 제거. |
| `backend/app/agents/retrieval/criteria_agent.py` | 룰 매핑 + LLM 분류(OpenAI) + 분류 세트별 검색/병합, 분류 결과를 `keyword_category_map`으로 응답에 포함 | 키워드 정규화 강화(특수문자 제거) + 조사 제거. `product_hierarchy.json`에서 `item → subcategory` 매핑 추가. LLM 프롬프트를 **소분류 전용**으로 간소화. LLM JSON 파싱 보강(블록 추출/클린업/로그). `category`를 `대>중>소` 경로로 구성하고 중복 메타 제거, `item`은 LLM 키워드 리스트로 저장. `_build_sources()`를 no-op으로 변경하고 기존 코드는 주석 보존. `parent_chunk_id`가 있을 때만 부모 청크를 붙이고, 없으면 원문만 return(기존 패턴 추정 로직 제거). |
| `backend/app/agents/retrieval/docs/criteria_node_plan.md` | “현재 요청 플랜” 섹션을 분리 추가 | 2026-02-04 요약 섹션 추가, 도입 전/후 로그 샘플 추가. |

---

### 도입 전
"chunk_id": ["별표2_1_I상품재화_5공산품34개품목_②전기통신기자재시계재봉기광학제품아동용품22_dispute6_단순",
    "별표2_1_I상품재화_5공산품34개품목_②전기통신기자재시계재봉기광학제품아동용품22_dispute7_단순",
    "별표2_1_I상품재화_5공산품34개품목_⑪가구31_dispute3_조건1",
    "별표2_Ⅰ_6_화장품",
    "별표2_1_I상품재화_5공산품34개품목_②전기통신기자재시계재봉기광학제품아동용품22_dispute5_부모"]

"max_similarity": 0.03252247488101534,
      "avg_similarity": 0.030647362811225865,
      "search_time_ms": 3599.863290786743,
      "keyword_category_map": []
    },
    "message": "retrieval_criteria: 5건 검색 완료 (max_sim: **0.033**)"


### 도입 후
"chunk_id": ["별표2_1_I상품재화_5공산품34개품목_①전자제품사무용기기22_dispute5_부모",
    "별표2_1_I상품재화_5공산품34개품목_①전자제품사무용기기21_dispute3_조건1_하위4",
    "별표2_1_I상품재화_5공산품34개품목_①전자제품사무용기기21_dispute3_조건1_하위3",
    "별표2_1_I상품재화_5공산품34개품목_①전자제품사무용기기21_dispute4_조건2",
    "별표2_1_I상품재화_5공산품34개품목_①전자제품사무용기기21_dispute3_부모"]

"max_similarity": 0.07842980639285504,
      "avg_similarity": 0.07152029959849523,
      "search_time_ms": 8403.089046478271,
      "keyword_category_map": [
        {
          "keyword": "프린트",
          "subcategory_name": "전자제품",
          "source": "llm"
        },
        {
          "keyword": "토너",
          "subcategory_name": "전자제품",
          "source": "llm"
        },
        {
          "keyword": "잉크",
          "subcategory_name": "전자제품",
          "source": "llm"
        }
      ]
    },
    "message": "retrieval_criteria: 5건 검색 완료 (max_sim: **0.078**)"