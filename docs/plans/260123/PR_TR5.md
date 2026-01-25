# PR-T5 Review: Docker 통합 테스트 정리

**작성일**: 2026-01-23  
**검토 대상 문서**: `docs/plans/260123/test-improvement-plan.md` 의 PR-T5 섹션  
**목표(원문)**: Docker 통합 테스트 4 fail + 2 skip 정리

---

## 1) 현재 코드베이스 적합성 검토 (RCA)

### A. 실패 체인의 실제 1차 원인: BGE-M3 Dockerfile 경로 불일치

**발견 사항**:
- `docker-compose.yml`은 `bge_m3_embedding`을 기본 실행 서비스로 포함
- `backend/Dockerfile.bge_m3`는 `COPY bge_m3_server.py .`를 수행
- 실제 서버 파일은 `backend/app/agents/retrieval/services/bge_m3_server.py`에 존재
- 결과: `docker-compose up` 단계에서 BGE-M3 빌드가 실패하고, `ddoksori_backend` 생성/기동까지 연쇄 실패

**판정**: ✅ PR-T5 범위에서 반드시 다뤄야 하는 "근본 원인"

### B. "BGE-M3 optional 분리" 방향성은 타당하나, 프로파일 설계가 보완 필요

**발견 사항**:
- 원문은 `profiles: [gpu]`로 기본 제외를 제안
- 하지만 현재 `Dockerfile.bge_m3`는 `CUDA_VISIBLE_DEVICES=""`로 CPU 고정("gpu"라는 명명과 의미 불일치)
- "기본 제외" 목적이라면 profile 이름은 `bge-m3`(또는 `optional`)이 더 정확
- GPU 지원까지 목표면 별도 서비스(예: `bge_m3_embedding_gpu`)로 분리하고 nvidia device 설정이 필요

**판정**: ⚠️ 방향은 맞지만, "명명/구성"을 현실에 맞춰 조정 권장

### C. Docker 통합 테스트는 opt-in 가드가 필요

**발견 사항**:
- `backend/scripts/testing/conftest.py`는 Docker ping 가능하면 `@pytest.mark.docker`를 실행 대상으로 둠
- 하지만 CI/개발환경에서 docker는 존재해도 image pull/권한 문제로 실패 가능
- `skip_ci` 마커가 등록만 되어 있고 실제 스킵 로직이 없어, CI에서 비의도 실행될 여지가 있음

**판정**: ✅ "환경변수 opt-in" 또는 "CI 자동 스킵"은 PR-T5에 매우 적합

### D. 테스트가 사용하는 compose는 "전체 스택"이라 실패 표면이 큼

**발견 사항**:
- `docker-compose.yml`에는 CloudBeaver/Redis/Prometheus/Grafana까지 포함
- 실제 테스트 assertion은 DB/Backend 중심이므로, 테스트 관점에서는 "필수 서비스만" 기동하는 편이 안정적

**판정**: ⚠️ (선택) 최소 compose로 분리하거나, 비필수 서비스도 profile로 빼는 것을 권장

---

## 2) 테스트 계획 적합성 검토

### A. 원문 계획의 "CORS 테스트 수정(OPTIONS)"은 이미 충족

**코드베이스 현황**:
- `backend/scripts/testing/integration/test_docker_environment.py`는 이미 `client.options()`로 CORS를 검증 (Line 132-138)

**판정**: ❌ 계획 항목 제거/수정 필요 (이미 구현됨)

### B. "Backend 컨테이너 테스트 조건 추가" 항목의 현황

**코드베이스 현황**:
- `test_backend_container_running` (Line 91-97)는 container 존재 여부만 검증
- `TEST_DOCKER_MODE` 환경변수 기반 조건부 실행은 미구현

**판정**: ✅ 적합 (opt-in 가드로 실제 구현 필요)

---

## 결론 및 수정 권장안 (Updated PR-T5 Plan)

### 목표 (현실화)

1. **기본 안정화**: `docker compose up` 기본 실행이 BGE-M3 없이도 성공하도록 구성
2. **테스트 격리**: Docker 통합 테스트는 opt-in으로 실행되도록 가드
3. **빌드 수정**: BGE-M3를 켜는 경우에도 빌드가 성공하도록 Dockerfile 경로 수정

### 작업 항목 (권장)

| # | 작업 | 파일 | 상세 |
|:---:|:---|:---|:---|
| 1 | BGE-M3 서버 파일 경로 수정 | `backend/Dockerfile.bge_m3` | `COPY bge_m3_server.py .` → `COPY app/agents/retrieval/services/bge_m3_server.py .` |
| 2 | BGE-M3 profile 분리 (기본 제외) | `docker-compose.yml` | `bge_m3_embedding`을 `profiles: ["bge-m3"]`로 설정 |
| 3 | Windows용 compose 동기화 | `docker-compose.windows.yml` | `bge_m3_embedding`을 동일하게 profile 분리 |
| 4 | Docker 통합 테스트 opt-in 가드 | `backend/scripts/testing/integration/test_docker_environment.py` 또는 `backend/scripts/testing/conftest.py` | `RUN_DOCKER_TESTS=1` 환경변수 기반 skip 로직 추가 |
| 5 | skip_ci 마커 활성화 (선택) | `backend/scripts/testing/conftest.py` | CI 환경(`CI=true`) 감지 시 docker 테스트 자동 skip |

### 상세 변경 방안

#### A. `backend/Dockerfile.bge_m3` (경로 수정)

**현재** (Line 23):
```dockerfile
COPY bge_m3_server.py .
```

**변경**:
```dockerfile
COPY app/agents/retrieval/services/bge_m3_server.py .
```

**이유**: 빌드 컨텍스트는 `./backend`이므로, COPY는 이 경로 기준으로 상대경로를 사용해야 함.

---

#### B. `docker-compose.yml` (Profile 분리)

**현재** (Line 71-87):
```yaml
bge_m3_embedding:
  build:
    context: ./backend
    dockerfile: Dockerfile.bge_m3
  container_name: ddoksori_bge_m3
  # ... ports, environment, volumes
```

**변경**:
```yaml
bge_m3_embedding:
  profiles: ["bge-m3"]  # 기본 docker compose up에서 제외
  build:
    context: ./backend
    dockerfile: Dockerfile.bge_m3
  container_name: ddoksori_bge_m3
  # ... ports, environment, volumes (나머지 동일)
```

**사용 방법**:
- `docker compose up -d` → BGE-M3 없이 기본 스택만 실행
- `docker compose --profile bge-m3 up -d` → BGE-M3 포함 실행

---

#### C. `docker-compose.windows.yml` (Windows용 동기화)

**현재** (Line 97-115):
```yaml
bge_m3_embedding:
  build:
    context: ./backend
    dockerfile: Dockerfile.bge_m3
  # ... (나머지)
```

**변경**:
```yaml
bge_m3_embedding:
  profiles: ["bge-m3"]  # 동일하게 profile 추가
  build:
    context: ./backend
    dockerfile: Dockerfile.bge_m3
  # ... (나머지)
```

---

#### D. Docker 통합 테스트 opt-in 가드

**위치**: `backend/scripts/testing/conftest.py`, `pytest_collection_modifyitems` 함수 (Line 254-283)

**현재**:
```python
def pytest_collection_modifyitems(config, items):
    skip_docker = pytest.mark.skip(reason="Docker 환경이 실행되지 않음")
    docker_available = False
    try:
        import docker
        client = docker.from_env()
        client.ping()
        docker_available = True
    except Exception:
        pass

    for item in items:
        # Docker 테스트 skip 로직
        if not docker_available and "docker" in item.keywords:
            item.add_marker(skip_docker)
```

**변경** (권장):
```python
def pytest_collection_modifyitems(config, items):
    skip_docker = pytest.mark.skip(reason="Docker 통합 테스트는 RUN_DOCKER_TESTS=1로 opt-in")
    skip_ci = pytest.mark.skip(reason="CI 환경에서는 Docker 통합 테스트 제외")
    
    # Docker 테스트 opt-in 확인
    run_docker_tests = os.getenv("RUN_DOCKER_TESTS") == "1"
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
    
    docker_available = False
    if run_docker_tests and not is_ci:
        try:
            import docker
            client = docker.from_env()
            client.ping()
            docker_available = True
        except Exception:
            pass

    for item in items:
        # CI 환경이면 docker 테스트는 항상 skip
        if is_ci and "docker" in item.keywords:
            item.add_marker(skip_ci)
        # opt-in 없거나 Docker 불가능하면 skip
        elif not run_docker_tests and "docker" in item.keywords:
            item.add_marker(skip_docker)
        elif run_docker_tests and not docker_available and "docker" in item.keywords:
            skip_docker_unavail = pytest.mark.skip(reason="Docker daemon 연결 불가")
            item.add_marker(skip_docker_unavail)
```

**환경변수 사용**:
```bash
# 로컬 개발: Docker 통합 테스트 활성화
RUN_DOCKER_TESTS=1 pytest backend/scripts/testing/ -m docker -v

# CI: 자동으로 Docker 테스트 제외
pytest backend/scripts/testing/ -v

# 기본: Docker 테스트 opt-in 필요
pytest backend/scripts/testing/ -v  # docker 테스트는 skip
```

---

### 완료 기준 (권장)

| 기준 | 검증 방법 |
|------|----------|
| ✅ `docker compose up -d` (기본) 성공 | `docker-compose up -d` → 모든 컨테이너(BGE-M3 제외) 정상 기동 |
| ✅ BGE-M3 profile 선택 가능 | `docker compose --profile bge-m3 up -d` → BGE-M3 포함 기동 |
| ✅ Docker 통합 테스트 opt-in | `RUN_DOCKER_TESTS=1 pytest -m docker` → 핵심 테스트 pass |
| ✅ Docker 통합 테스트 skip (CI) | CI 환경에서 `pytest -m docker`는 자동 skip |
| ✅ Docker 테스트 4 fail → 0 fail | 모든 docker 통합 테스트가 안정적으로 pass |

---

## 참고 사항

### 영향 분석

| 영역 | 변경 | 영향 |
|------|------|------|
| **기본 스택** | BGE-M3 profile 분리 | `docker compose up`이 더 빠르고 안정적 (선택 사항 분리) |
| **테스트 안정성** | Docker opt-in 가드 | 불필요한 환경 의존성 제거 (CI/로컬 안정화) |
| **빌드 신뢰성** | Dockerfile 경로 수정 | BGE-M3 profile 활성화 시에도 빌드 성공 보장 |
| **Windows 호환성** | docker-compose.windows.yml 동기화 | Windows 사용자도 동일한 profile 구조 제공 |

### 위험도 평가

| 위험 | 수준 | 완화 방안 |
|------|------|----------|
| Profile 마이그레이션 | 낮음 | 문서화: 기본 사용법과 선택 사항 구분 |
| Dockerfile 경로 변경 | 낮음 | BGE-M3 활성화 시에만 영향 (선택 사항) |
| CI/CD 자동 skip | 중간 | 명시적 환경변수(`RUN_DOCKER_TESTS=1`)로 opt-in 요구 |

---

## 다음 단계

### 즉시 실행 (이 PR 완료 후)
1. PR-T5 구현 및 검증 (위 작업 항목 1-5 실행)
2. 로컬에서 `docker compose up -d` 정상 기동 확인
3. `RUN_DOCKER_TESTS=1 pytest -m docker` 정상 통과 확인

### 중기 계획
- PR-T6 (A/B Testing Framework Path Fix)
- PR-T7 (Query Analysis Law Classification Improvement)
- 테스트 성공률: 93.8% → 97%+ 목표 달성

### 선택적 개선 (Future)
- (선택) 테스트 전용 최소 compose 파일(`docker-compose.test.yml`) 도입
- (선택) Redis/Prometheus/Grafana도 profile로 분리해 개발 편의성 향상

---

**최종 상태**: ✅ Review 완료 → 구현 준비 완료
