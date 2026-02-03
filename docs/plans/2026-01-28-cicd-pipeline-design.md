# DDOKSORI CI/CD Pipeline Design

> **Status**: 구현 완료 (2026-02-01)
>
> **상세 설정 가이드**: [docs/guides/cicd-setup-guide.md](../guides/cicd-setup-guide.md)

## Overview

GitHub Actions 기반 CI/CD 파이프라인.

**구성**: PR/Push 시 자동 테스트 → main 머지 시 Staging 배포 → Tag 생성 시 Production 배포

**플랫폼**: GitHub Actions + AWS (EC2 + ECR + RDS + Secrets Manager + S3)

---

## Architecture

```
┌─────────────────── GitHub Actions CI/CD Pipeline ────────────────────┐
│                                                                      │
│  [PR/Push] ──→ ┌──────────┐    ┌──────────┐    ┌──────────────┐     │
│                │  Lint    │ ─→ │  Test    │ ─→ │ Frontend     │     │
│                │ (Black,  │    │ (pytest, │    │ Build Check  │     │
│                │  isort,  │    │ pgvector,│    └──────────────┘     │
│                │  ESLint) │    │  Redis)  │                         │
│                └──────────┘    └──────────┘                         │
│                                                                      │
│  [main merge] ──→ ┌───────────────────┐    ┌──────────────┐         │
│                   │ Build & Push      │ ─→ │ Deploy       │         │
│                   │ (Buildx + ECR +   │    │ Staging      │         │
│                   │  GHA Cache)       │    │ (SSH + ECR)  │         │
│                   └───────────────────┘    └──────────────┘         │
│                                                                      │
│  [Tag: v*] ──→ ┌──────────────┐    ┌─────────────────┐              │
│                │ Wait for     │ ─→ │ Deploy          │              │
│                │ Build        │    │ Production      │              │
│                └──────────────┘    │ (Manual Approve)│              │
│                                    └────────┬────────┘              │
│                                             │ (failure)             │
│                                    ┌────────▼────────┐              │
│                                    │ Auto Rollback   │              │
│                                    └─────────────────┘              │
│                                                                      │
│  [Weekly Cron] ──→ ┌──────────────────┐                             │
│                    │ DB Backup → S3   │                             │
│                    └──────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 설계 의사결정

### SSH 접근 방식: 동적 IP 화이트리스트 채택

| 방식 | 보안 | 관리 부담 | 비고 |
|------|:----:|:---------:|------|
| **동적 IP 화이트리스트** | ★★★★ | 낮음 | **채택** - 배포 중 몇 분만 포트 22 열림 |
| Prefix List | ★★ | 높음 | 수백 개 IP, 주기적 갱신 필요 |
| 0.0.0.0/0 개방 | ★ | 없음 | 포트 22가 항상 전체 공개 |
| SSM Send-Command | ★★★★★ | 중간 | SSH 자체를 안 씀 (고급) |

### 테스트 전략

| 트리거 | 실행 범위 | 목적 |
|--------|-----------|------|
| PR | `pytest -m "not skip_ci and not llm"` | 빠른 피드백, LLM API 비용 절감 |
| main push | `pytest -m "not skip_ci"` | 전체 테스트, LLM 포함 |

### 배포 전략

| 환경 | 트리거 | 승인 | 롤백 |
|------|--------|------|------|
| Staging | main 머지 → Build 성공 | 자동 | 수동 |
| Production | v* 태그 | 수동 승인 필요 | 자동 (실패 시) |

### HTTPS: EC2 + Let's Encrypt 선택

| 항목 | ALB 방식 | EC2 직접 (Nginx + Let's Encrypt) |
|------|---------|-------------------------------|
| SSL 인증서 | ACM 무료 (자동갱신) | Let's Encrypt 무료 (90일 자동갱신) |
| 로드밸런서 | ~$24-38/월 (고정비) | $0 (Nginx가 대신) |
| **월 총액** | ~$59-73/월 | **~$35/월** (채택) |

**판단**: EC2 1대 운영 시 ALB 불필요, 예산 최적화

---

## 구현 파일 목록

| 파일 | 설명 |
|------|------|
| `.github/workflows/lint.yml` | Lint 워크플로우 |
| `.github/workflows/test.yml` | 테스트 워크플로우 |
| `.github/workflows/build.yml` | 이미지 빌드 워크플로우 |
| `.github/workflows/deploy-staging.yml` | Staging 배포 |
| `.github/workflows/deploy-production.yml` | Production 배포 + 자동 롤백 |
| `.github/workflows/db-backup.yml` | Weekly DB 백업 → S3 |
| `backend/Dockerfile.prod` | 프로덕션용 Backend Dockerfile |
| `frontend/Dockerfile.prod` | 프로덕션용 Frontend Dockerfile |
| `frontend/nginx.conf` | Nginx 설정 (SSE, gzip, 프록시) |
| `docker-compose.prod.yml` | 프로덕션 Compose 파일 |
| `backend/app/common/secrets.py` | AWS Secrets Manager SDK 래퍼 |

---

## 비용 예상

| 항목 | 비용/월 |
|------|---------|
| EC2 t3.small | ~$15 |
| RDS db.t3.micro | ~$15 |
| ECR | ~$1 |
| S3 (백업) | ~$1 |
| Secrets Manager | ~$6 |
| **합계** | **$30-70** |
