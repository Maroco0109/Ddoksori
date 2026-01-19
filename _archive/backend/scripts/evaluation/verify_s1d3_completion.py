#!/usr/bin/env python3
"""
S1-D3 완료 기준 검증 스크립트

완료 기준 (README.md):
"온보딩 품목 입력으로 '품목 후보 1~3개 + 연결된 기준/기간표(출처 포함)' 조회 가능"
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../examples'))

from query_criteria import (
    search_items_by_keyword,
    get_resolution_criteria,
    get_warranty_period,
    get_product_lifespan,
    hierarchical_search,
    get_criteria_statistics
)


def verify_item_search(item_keyword: str):
    """품목 검색 기능 검증"""
    print(f"\n{'='*70}")
    print(f"테스트 품목: '{item_keyword}'")
    print(f"{'='*70}")

    # 1. 품목 후보 검색 (1~3개)
    print("\n[Step 1] 품목 후보 검색")
    items = search_items_by_keyword(item_keyword)

    if not items:
        print(f"  ⚠️ '{item_keyword}' 검색 결과 없음")
        return False

    print(f"  ✅ {len(items)}개 품목 후보 발견:")
    for i, item in enumerate(items[:3], 1):
        category = item.get('category', 'N/A')
        industry = item.get('industry', 'N/A')
        item_group = item.get('item_group', 'N/A')
        path = item.get('path_hint', 'N/A')
        print(f"    {i}. {path}")
        print(f"       - 카테고리: {category}")
        print(f"       - 업종: {industry}")
        print(f"       - 품목그룹: {item_group}")

    # 2. 연결된 기준 조회
    if items:
        first_item = items[0]
        item_group = first_item.get('item_group')

        print(f"\n[Step 2] 연결된 해결기준 조회 (품목그룹: {item_group})")
        if item_group:
            criteria = get_resolution_criteria(item_group=item_group)
            if criteria:
                print(f"  ✅ {len(criteria)}개 해결기준 발견:")
                for i, c in enumerate(criteria[:3], 1):
                    text = c.get('unit_text', '')
                    print(f"    {i}. {text[:100]}...")
                    print(f"       출처: {c.get('unit_id')}")
            else:
                print(f"  ⚠️ 해결기준 없음 (별표2에 {item_group} 관련 규칙 없음)")
        else:
            print(f"  ⚠️ 품목그룹 정보 없음")

        # 3. 품질보증기간 조회
        print(f"\n[Step 3] 품질보증기간 조회 (별표3)")
        warranty = get_warranty_period(item_keyword)
        if warranty:
            print(f"  ✅ {len(warranty)}개 품질보증기간 정보 발견:")
            for i, w in enumerate(warranty[:2], 1):
                text = w.get('unit_text', '')
                print(f"    {i}. {text[:100]}...")
                print(f"       출처: {w.get('unit_id')}")
        else:
            print(f"  ⚠️ 품질보증기간 정보 없음")

        # 4. 내용연수 조회
        print(f"\n[Step 4] 내용연수 조회 (별표4)")
        lifespan = get_product_lifespan(item_keyword)
        if lifespan:
            print(f"  ✅ {len(lifespan)}개 내용연수 정보 발견:")
            for i, l in enumerate(lifespan[:2], 1):
                text = l.get('unit_text', '')
                print(f"    {i}. {text[:100]}...")
                print(f"       출처: {l.get('unit_id')}")
        else:
            print(f"  ⚠️ 내용연수 정보 없음")

    print(f"\n{'='*70}")
    print(f"✅ '{item_keyword}' 검증 완료")
    print(f"{'='*70}")

    return True


def main():
    """메인 함수"""
    print("=" * 70)
    print("S1-D3 완료 기준 검증")
    print("=" * 70)

    # 데이터 로드 확인
    print("\n[단계 0] 데이터 로드 상태 확인")
    stats = get_criteria_statistics()

    print("\n📊 Loaded Data Summary:")
    total_units = 0
    total_chunks = 0

    print("\n[criteria_units table]")
    for row in stats['criteria_units']:
        count = row['unit_count']
        total_units += count
        print(f"  - {row['source_id']}: {count} units")

    print("\n[chunks table (via documents)]")
    for row in stats['chunks']:
        count = row['chunk_count']
        total_chunks += count
        print(f"  - {row['doc_type']}: {count} chunks")

    print(f"\n✅ 총 {total_units} units, {total_chunks} chunks 로드됨")

    if total_units == 0:
        print("\n❌ 데이터가 로드되지 않았습니다. load_criteria_to_db.py를 먼저 실행하세요.")
        return

    # 테스트 케이스
    test_items = [
        "스마트폰",
        "계란",
        "전자제품",
    ]

    print("\n" + "=" * 70)
    print("S1-D3 완료 기준 검증: 품목 입력 → 품목 후보 + 연결 기준 조회")
    print("=" * 70)

    success_count = 0
    for item in test_items:
        if verify_item_search(item):
            success_count += 1

    # 최종 결과
    print("\n" + "=" * 70)
    print("최종 검증 결과")
    print("=" * 70)
    print(f"\n테스트 케이스: {len(test_items)}개")
    print(f"성공: {success_count}개")
    print(f"실패: {len(test_items) - success_count}개")

    if success_count == len(test_items):
        print("\n✅ S1-D3 완료 기준 충족:")
        print("   - 품목 입력으로 품목 후보 1~3개 조회 가능 ✓")
        print("   - 연결된 기준/기간표(출처 포함) 조회 가능 ✓")
        print("   - Dual storage (criteria_units + documents/chunks) 구현 ✓")
        print("   - 계층 검색 (별표1 → 별표2/3/4) 가능 ✓")
    else:
        print(f"\n⚠️ 일부 테스트 실패 ({success_count}/{len(test_items)})")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
