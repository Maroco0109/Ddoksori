# 분쟁조정기준 계층 검색 사용 가이드

## 개요

분쟁조정기준 데이터에 법령 데이터와 유사한 계층 검색 방식을 적용하여, 사용자 상황에 맞는 분쟁조정기준을 효율적으로 검색하고 매칭할 수 있습니다.

## 계층 검색 구조

### Stage 1: 키워드 검색 (RDB)
- **대상**: category/industry/item_group 레벨
- **데이터**: 별표1 (품목 분류)
- **검색 방식**: 키워드 매칭 (LIKE 검색)

### Stage 2: Vector 검색 (Vector DB)
- **대상**: items/dispute_type/resolution 레벨
- **데이터**: 별표2 (해결기준)
- **검색 방식**: 의미 기반 유사도 검색

## 사용자 입력 구조

사용자가 입력하는 "자신의 상황"은 다음 5가지 필드로 구성됩니다:

1. **구매 일자** (purchase_date): 연도-월-일 형식 (예: "2024-01-15")
2. **구매처** (seller_info): 판매자 상호명 또는 브랜드명, 인터넷 쇼핑몰 정보
3. **구매 품목** (item): 구매한 상품명 (예: "계란", "에어컨")
4. **구매 금액** (purchase_amount): 구매 가격 (숫자)
5. **분쟁 상세 내용** (dispute_detail): 자연어 텍스트 (예: "환불 불가", "부패된 상품")

## 사용 방법

### 1. 사용자 입력 파싱

```python
from scripts.parse_user_input import parse_user_input

user_input = parse_user_input(
    purchase_date="2024-01-15",
    seller_info="네이버 쇼핑",
    item="계란",
    purchase_amount=10000.0,
    dispute_detail="환불 불가, 부패된 상품"
)

print(user_input)
# {
#     "item": "계란",
#     "item_matched": {
#         "category": "상품(재화)",
#         "industry": "농ㆍ수ㆍ축산물",
#         "item_group": "란류"
#     },
#     "dispute_types": ["환불", "부패 변질"],
#     "is_online": True,
#     "purchase_date": datetime(2024, 1, 15),
#     "purchase_amount": 10000.0
# }
```

### 2. 계층 검색

```python
from scripts.search_criteria_hierarchical import search_criteria_hierarchical

results = search_criteria_hierarchical(
    user_query="환불 불가, 부패된 상품",
    item_name="계란",
    dispute_type="부패 변질",
    limit=10
)

print(f"Stage 1 결과: {results['stage1']['count']}개")
print(f"Stage 2 결과: {results['stage2']['count']}개")
```

### 3. 기간 검토

```python
from scripts.check_periods import check_warranty_period, check_cooling_off_period
from datetime import datetime

# 품질보증기간 확인
warranty_result = check_warranty_period(
    item="계란",
    purchase_date=datetime(2024, 1, 15)
)
print(warranty_result["message"])

# 청약철회 기간 확인 (인터넷 쇼핑몰 구매 시)
cooling_result = check_cooling_off_period(
    purchase_date=datetime(2024, 1, 15),
    is_online=True
)
print(cooling_result["message"])
```

### 4. 사용자 상황 매칭

```python
from scripts.match_user_situation import search_and_match_user_situation

result = search_and_match_user_situation(
    purchase_date="2024-01-15",
    seller_info="네이버 쇼핑",
    item="계란",
    purchase_amount=10000.0,
    dispute_detail="환불 불가, 부패된 상품"
)

# 매칭된 해결기준 확인
for matched in result["matched_results"]:
    match_info = matched["match"]
    criteria = matched["criteria"]
    
    print(f"매칭 점수: {match_info['match_score']:.2f}")
    print(f"적용 가능: {match_info['is_applicable']}")
    print(f"해결기준: {criteria.get('resolution')}")
    print(f"경고: {match_info.get('warnings', [])}")
```

## 매칭 점수 계산

매칭 점수는 다음 가중치로 계산됩니다:

- **품목 매칭**: 0.3 (카테고리 0.15 + 품목 그룹 0.15)
- **분쟁 유형 매칭**: 0.4
- **기간 조건 충족**: 0.2 (품질보증기간 0.1 + 청약철회 기간 0.1)
- **구매처 조건 충족**: 0.1

**적용 가능 여부**: 매칭 점수 >= 0.5

## 조건 검토 항목

### 1. 품목 매칭
- 카테고리 일치 여부
- 품목 그룹 일치 여부

### 2. 분쟁 유형 매칭
- 사용자 입력의 분쟁 유형과 해결기준의 dispute_type 일치 여부

### 3. 기간 조건
- **품질보증기간**: 구매일 기준 품질보증기간 경과 여부 (별표3)
- **유통기간/소비기한**: 구매일 기준 유통기한 경과 여부
- **청약철회 기간**: 인터넷 쇼핑몰 구매 시 7일 이내 여부

### 4. 구매처 조건
- 인터넷 쇼핑몰 구매인 경우 청약철회 관련 분쟁 유형에 가점

## 예제 시나리오

### 시나리오 1: 인터넷 쇼핑몰 구매, 환불 거부

```python
result = search_and_match_user_situation(
    purchase_date="2024-01-20",
    seller_info="쿠팡",
    item="에어컨",
    purchase_amount=500000.0,
    dispute_detail="환불 불가, 하자 발생"
)

# 결과:
# - 인터넷 쇼핑몰 감지: True
# - 분쟁 유형: ["환불", "하자"]
# - 청약철회 기간 확인 (7일 이내)
# - 품질보증기간 확인 (별표3)
```

### 시나리오 2: 오프라인 구매, 부패 변질

```python
result = search_and_match_user_situation(
    purchase_date="2024-01-15",
    seller_info="마트",
    item="계란",
    purchase_amount=10000.0,
    dispute_detail="부패된 상품, 교환 요구"
)

# 결과:
# - 인터넷 쇼핑몰 감지: False
# - 분쟁 유형: ["부패 변질", "교환"]
# - 품질보증기간 확인 (별표3)
# - 일반 분쟁조정기준 적용
```

## CLI 사용법

### 사용자 입력 파싱

```bash
python scripts/parse_user_input.py \
  2024-01-15 \
  "네이버 쇼핑" \
  "계란" \
  10000 \
  "환불 불가, 부패된 상품"
```

### 계층 검색

```bash
python scripts/search_criteria_hierarchical.py \
  "환불 불가, 부패된 상품" \
  "계란" \
  "부패 변질"
```

### 기간 검토

```bash
python scripts/check_periods.py \
  "계란" \
  2024-01-15
```

### 사용자 상황 매칭

```bash
python scripts/match_user_situation.py \
  2024-01-15 \
  "네이버 쇼핑" \
  "계란" \
  10000 \
  "환불 불가, 부패된 상품"
```

## JSONL 생성

계층 정보를 포함한 JSONL 파일 생성:

```bash
# 단일 파일
python scripts/generate_criteria_hierarchical_jsonl.py \
  criteria_jsonl_data/consumer_dispute_resolution_criteria_table1_items.jsonl \
  criteria_hierarchical_jsonl/table1_hierarchical.jsonl

# 전체 디렉토리
python scripts/generate_criteria_hierarchical_jsonl.py \
  --all \
  criteria_jsonl_data \
  criteria_hierarchical_jsonl
```

## 주의사항

1. **임베딩 API 연결**: Vector 검색을 사용하려면 임베딩 API를 연결해야 합니다. 현재는 텍스트 검색으로 폴백됩니다.

2. **품질보증기간 파싱**: 별표3의 품질보증기간 텍스트는 복잡한 조건이 포함될 수 있으므로, 정확한 파싱이 필요합니다.

3. **분쟁 유형 추출**: 자연어 텍스트에서 분쟁 유형을 추출하는 것은 키워드 매칭 기반이므로, 정확도를 높이려면 Vector 검색을 활용하는 것이 좋습니다.

4. **매칭 점수 임계값**: 현재 적용 가능 여부 판단 임계값은 0.5입니다. 실제 사용 데이터로 튜닝이 필요할 수 있습니다.

## 참고 자료

- [분쟁조정기준 데이터 사용 가이드](criteria_data_usage_guide.md)
- [검색 전략 가이드](search_strategy.md)
- [법령 데이터 계층 검색](../pdy/scripts/query_router.py)
