# DDOKSORI CI/CD Pipeline Design

> **Status**: 구현 완료 (2026-02-01 최신화)
>
> 이 문서는 설계 계획이 아닌 **현재 운영 중인 CI/CD 파이프라인의 참조 문서**입니다.
> 모든 워크플로우, Dockerfile, Compose 파일은 구현 완료되어 실 운영 중입니다.
>
> **전제 조건**: `feature/34-e2e` 브랜치의 모든 변경사항이 반영된 상태를 기준으로 합니다.

## Overview

DDOKSORI 프로젝트의 GitHub Actions 기반 CI/CD 파이프라인 참조 문서.

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

## Step 0: AWS 인프라 초기 설정

> CI/CD 파이프라인을 실제 운영하기 위한 AWS 인프라 초기 설정 단계별 가이드.
> Phase A → B → C 순서로 진행하며, Phase A는 EC2 없이도 검증 가능.

### Phase A: CI + 빌드 검증 (EC2 없이 가능)

#### A-1. AWS CLI v2 설치

```bash
# Linux (x86_64)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 확인
aws --version

# 초기 설정
aws configure
# AWS Access Key ID: <IAM 사용자 Access Key>
# AWS Secret Access Key: <IAM 사용자 Secret Key>
# Default region name: ap-northeast-2
# Default output format: json
```

#### A-2. OIDC Identity Provider 생성 (AWS Console)

**IAM → Identity providers → Add provider**

| 필드 | 입력값 |
|------|--------|
| Provider type | OpenID Connect |
| Provider URL | `https://token.actions.githubusercontent.com` |
| Get thumbprint | 버튼 클릭 (자동 생성) |
| Audience (클라이언트 ID) | `sts.amazonaws.com` |

#### A-3. IAM Role 생성 (OIDC 연동)

**IAM → Roles → Create role**

1. Trusted entity: **Web identity**
2. Identity provider: 위에서 생성한 GitHub OIDC 선택
3. Audience: `sts.amazonaws.com`
4. Condition 설정:
   - `token.actions.githubusercontent.com:sub` → `StringLike` → `repo:<org>/<repo>:*`
   - `token.actions.githubusercontent.com:aud` → `StringEquals` → `sts.amazonaws.com`
5. 권한 정책 연결: `AmazonEC2ContainerRegistryPowerUser`
6. Role 이름 지정 (예: `ddoksori-github-actions`)

> **Note:** `<org>/<repo>`는 실제 GitHub 리포지토리 경로로 교체 (예: `myorg/ddoksori`)

#### A-4. ECR 리포지토리 생성

```bash
aws ecr create-repository --repository-name ddoksori-backend --region ap-northeast-2
aws ecr create-repository --repository-name ddoksori-frontend --region ap-northeast-2
```

#### A-5. GitHub Secrets 등록

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | 값 | 필수 |
|-------------|---|------|
| `AWS_ROLE_ARN` | 생성한 Role ARN (예: `arn:aws:iam::123456789012:role/ddoksori-github-actions`) | ✅ |

#### A-6. 워크플로우 파일 확인

`.github/workflows/` 에 다음 파일이 존재하는지 확인:
- `lint.yml` - Lint 워크플로우
- `test.yml` - 테스트 워크플로우
- `build.yml` - Docker 이미지 빌드 & ECR 푸시

#### A-7. CI + 빌드 검증

1. PR 생성 또는 main에 push → GitHub Actions 탭에서 lint, test 실행 확인
2. main 머지 시 → build.yml이 ECR에 이미지를 push하는지 확인

**Phase A 완료 체크리스트:**
- [ ] AWS CLI 설치 & 설정
- [ ] OIDC Identity Provider 생성
- [ ] IAM Role 생성 (OIDC trust + ECR 권한)
- [ ] ECR 리포지토리 2개 생성
- [ ] GitHub Secrets: `AWS_ROLE_ARN` 등록
- [ ] lint.yml, test.yml PR 시 정상 동작
- [ ] build.yml main push 시 ECR 이미지 푸시 성공

---

### Phase B: EC2 생성 & 설정

#### B-1. EC2 인스턴스 생성 (AWS Console)

**EC2 → Launch instances**

| 설정 | 값 |
|------|---|
| Name | `ddoksori-staging` |
| AMI | Ubuntu 24.04 LTS |
| Instance type | `t3.small` (~$15/월) |
| Key pair | 새로 생성 → `.pem` 파일 다운로드 & 안전 보관 |
| Network | 기본 VPC |
| Security group | 아래 참조 |

**보안 그룹 인바운드 규칙:**

| 포트 | 프로토콜 | 소스 | 용도 |
|------|---------|------|------|
| 22 | TCP | My IP | SSH - 개발자 접속용 (콘솔에서 "My IP" 선택) |
| 80 | TCP | 0.0.0.0/0 | HTTP (Nginx → Backend 프록시) |

> **Note:** 8000 포트는 열지 않습니다. Nginx가 Docker 내부 네트워크(`ddoksori-net`)에서
> Backend:8000으로 프록시하므로 외부 노출이 불필요합니다.
>
> **GitHub Actions의 SSH 접근 (포트 22):**
> CI/CD 배포 시 GitHub Actions Runner가 SSH로 EC2에 접속해야 합니다.
> Runner의 IP는 매번 바뀌므로, **배포 직전에 Runner IP를 보안 그룹에 추가하고 배포 후 제거**하는
> "동적 IP 화이트리스트" 방식을 사용합니다. 설정 방법은 아래 **B-1a**를 참조하세요.

#### B-1a. GitHub Actions SSH 동적 IP 화이트리스트 설정

GitHub Actions Runner는 매번 다른 IP에서 실행됩니다.
**배포 시에만** Runner IP를 보안 그룹에 열고, **끝나면 즉시 닫는** 방식이 업계 표준입니다.

> **다른 방식과 비교:**
>
> | 방식 | 보안 | 관리 부담 | 비고 |
> |------|:----:|:---------:|------|
> | **동적 IP 화이트리스트 (채택)** | ★★★★ | 낮음 | 배포 중 몇 분만 포트 22 열림 |
> | 전체 IP 대역 등록 (Prefix List) | ★★ | 높음 | 수백 개 IP, 주기적 갱신 필요 |
> | 0.0.0.0/0 개방 | ★ | 없음 | 포트 22가 항상 전체 공개 |
> | AWS SSM Send-Command | ★★★★★ | 중간 | SSH 자체를 안 씀 (고급) |

##### 작동 원리

```
배포 워크플로우 시작
  │
  ├─ 1) Runner의 퍼블릭 IP 확인 (예: 20.1.2.3)
  ├─ 2) 보안 그룹에 SSH 규칙 추가: 20.1.2.3/32 → 포트 22
  ├─ 3) SSH로 EC2 접속 → docker compose pull → up -d
  ├─ 4) 헬스체크
  └─ 5) 보안 그룹에서 SSH 규칙 제거: 20.1.2.3/32 (if: always → 실패해도 반드시 실행)
```

##### 1단계: CI/CD 전용 보안 그룹 생성

기존 보안 그룹의 규칙과 섞이지 않도록 **별도 보안 그룹**을 만들어 EC2에 추가합니다.

```
EC2 → Security Groups → Create security group

  이름: ddoksori-github-actions-ssh
  설명: Temporary SSH access for GitHub Actions deployment
  VPC: EC2와 동일한 VPC 선택
  인바운드 규칙: 비워둠 (워크플로우가 동적으로 관리)
```

생성 후 **보안 그룹 ID** (예: `sg-0abc1234def56789`) 를 메모합니다.

그 다음 이 보안 그룹을 EC2 인스턴스에 **추가** 연결합니다:

```
EC2 → 인스턴스 선택 → Actions → Security → Change security groups
  → "ddoksori-github-actions-ssh" 추가 → Save
```

> **왜 별도 보안 그룹?**
> 워크플로우가 `authorize` / `revoke`를 반복하므로, 기존 보안 그룹의 규칙에 영향을 주지 않기 위해
> 격리된 보안 그룹을 사용합니다. EC2 인스턴스에는 보안 그룹을 여러 개 붙일 수 있습니다.

##### 2단계: IAM 정책 생성 & Role에 연결

GitHub Actions의 OIDC Role이 보안 그룹을 수정할 수 있도록 권한을 추가합니다.

```
IAM → Policies → Create policy → JSON 탭에 붙여넣기:
```

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsSecurityGroupAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:DescribeSecurityGroups"
      ],
      "Resource": [
        "arn:aws:ec2:ap-northeast-2:<AWS_ACCOUNT_ID>:security-group/<SG_ID>"
      ]
    }
  ]
}
```

> **`<AWS_ACCOUNT_ID>`**: AWS 계정 ID (12자리 숫자, 콘솔 우측 상단에서 확인)
> **`<SG_ID>`**: 1단계에서 생성한 보안 그룹 ID (예: `sg-0abc1234def56789`)

정책 이름: `ddoksori-github-actions-sg-policy`

생성 후 기존 OIDC Role (`ddoksori-github-actions`)에 이 정책을 **연결(Attach)**합니다:

```
IAM → Roles → ddoksori-github-actions → Permissions → Add permissions
  → Attach policies → "ddoksori-github-actions-sg-policy" 선택 → Add
```

##### 3단계: GitHub Secret 추가

```
GitHub repo → Settings → Secrets and variables → Actions → New repository secret

  Name:  AWS_SECURITY_GROUP_ID
  Value: sg-0abc1234def56789    (1단계에서 메모한 보안 그룹 ID)
```

##### 4단계: deploy 워크플로우에 IP 추가/제거 스텝 적용

`deploy-staging.yml`과 `deploy-production.yml` 모두에 적용합니다.

**변경 전 (현재):**
```yaml
steps:
  - uses: actions/checkout@v4
  - name: Configure AWS credentials
    # ...
  - name: Get ECR Login
    # ...
  - name: Deploy to Staging     # ← SSH 접속
    uses: appleboy/ssh-action@v1.0.0
    # ...
  - name: Health Check
    # ...
```

**변경 후:**
```yaml
steps:
  - uses: actions/checkout@v4

  - name: Configure AWS credentials
    uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      aws-region: ${{ env.AWS_REGION }}

  # ===== 동적 IP 화이트리스트: 시작 =====
  - name: Get Runner IP
    id: runner-ip
    uses: haythem/public-ip@v1.3

  - name: Open SSH for Runner IP
    run: |
      aws ec2 authorize-security-group-ingress \
        --group-id ${{ secrets.AWS_SECURITY_GROUP_ID }} \
        --protocol tcp \
        --port 22 \
        --cidr ${{ steps.runner-ip.outputs.ipv4 }}/32
      echo "✓ Opened SSH for ${{ steps.runner-ip.outputs.ipv4 }}/32"
  # ===== 동적 IP 화이트리스트: 끝 =====

  - name: Get ECR Login
    id: ecr-login
    uses: aws-actions/amazon-ecr-login@v2

  - name: Deploy to Staging
    uses: appleboy/ssh-action@v1.0.0
    with:
      host: ${{ env.EC2_HOST }}
      username: ubuntu
      key: ${{ secrets.EC2_SSH_KEY }}
      script: |
        cd /home/ubuntu/ddoksori
        # ... (기존 배포 스크립트 동일)

  - name: Health Check
    run: |
      # ... (기존 헬스체크 동일)

  # ===== 동적 IP 화이트리스트: 정리 (반드시 실행) =====
  - name: Close SSH for Runner IP
    if: always()
    run: |
      aws ec2 revoke-security-group-ingress \
        --group-id ${{ secrets.AWS_SECURITY_GROUP_ID }} \
        --protocol tcp \
        --port 22 \
        --cidr ${{ steps.runner-ip.outputs.ipv4 }}/32
      echo "✓ Closed SSH for ${{ steps.runner-ip.outputs.ipv4 }}/32"
  # ===== 동적 IP 화이트리스트: 끝 =====

  - name: Discord Notification - Success
    # ... (기존 동일)
```

> **핵심 포인트:**
> - `if: always()` → 배포가 실패해도 **반드시** IP를 제거합니다 (보안 누수 방지)
> - `haythem/public-ip@v1.3` → Runner의 퍼블릭 IPv4를 가져오는 검증된 Action
> - `/32` → 정확히 해당 Runner IP 1개만 허용 (가장 좁은 범위)
> - 보안 그룹 규칙이 배포 중 몇 분만 존재하므로 공격 표면이 최소화됩니다

##### 전체 설정 체크리스트

- [ ] 1단계: `ddoksori-github-actions-ssh` 보안 그룹 생성 (인바운드 비움)
- [ ] 1단계: EC2 인스턴스에 보안 그룹 추가 연결
- [ ] 2단계: IAM 정책 생성 (`ec2:AuthorizeSecurityGroupIngress`, `RevokeSecurityGroupIngress`)
- [ ] 2단계: 기존 OIDC Role에 정책 Attach
- [ ] 3단계: GitHub Secret `AWS_SECURITY_GROUP_ID` 등록
- [ ] 4단계: `deploy-staging.yml`에 IP 추가/제거 스텝 적용
- [ ] 4단계: `deploy-production.yml`에 IP 추가/제거 스텝 적용
- [ ] 테스트: main에 push → 배포 성공 → Actions 로그에서 "Opened SSH" / "Closed SSH" 확인

#### B-2. 탄력적 IP (Elastic IP) 할당

EC2 퍼블릭 IP는 재부팅 시 변경되므로, 고정 IP를 할당해야 배포 워크플로우가 안정적으로 동작합니다.

1. **EC2 → Elastic IPs → Allocate Elastic IP address** 클릭
2. 할당된 IP 선택 → **Actions → Associate Elastic IP address**
3. 대상 EC2 인스턴스(`ddoksori-staging`) 선택 → Associate

> **비용:** EC2에 연결된 상태면 **무료**. 연결하지 않고 방치하면 과금 발생.

할당된 IP를 `deploy-staging.yml`의 `EC2_HOST`와 도메인 DNS A 레코드에 설정합니다.

#### B-3. EC2 초기 설정 (터미널)

EC2는 빈 서버이므로 Docker 등을 직접 설치해야 합니다.
로컬 터미널에서 SSH로 접속한 뒤 아래 명령어를 실행합니다.

```bash
# 1) SSH 접속 (로컬 터미널에서 실행)
ssh -i "다운받은키.pem" ubuntu@<탄력적IP>

# 2) Docker + 기본 패키지 설치
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 curl unzip
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ubuntu

# 3) AWS CLI v2 설치 (Ubuntu 24.04에서는 apt로 설치 불가)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# 4) 재접속 (docker 그룹 반영을 위해 필요)
exit
ssh -i "다운받은키.pem" ubuntu@<탄력적IP>

# 5) 설치 확인
docker --version
docker compose version
aws --version

# 6) 프로젝트 디렉토리 생성
mkdir -p /home/ubuntu/ddoksori/backups
```

#### B-4. EC2에 IAM Role 연결

EC2가 ECR에서 이미지를 pull하려면 별도 IAM Role이 필요:

1. **IAM → Roles → Create role**
   - Trusted entity: **AWS service → EC2**
   - 정책: `AmazonEC2ContainerRegistryReadOnly`
   - Role 이름: `ddoksori-ec2-role`

2. **EC2 Console → 인스턴스 선택 → Actions → Security → Modify IAM role**
   - 위에서 생성한 `ddoksori-ec2-role` 선택

> **Note:** AWS Secrets Manager도 사용할 경우 `SecretsManagerReadWrite` 정책도 추가.

#### B-5. 프로젝트 코드 배치 (git clone)

EC2에서 프로젝트를 clone합니다. **반드시 `.` (현재 디렉토리)를 붙여야 합니다.**

```bash
# EC2에서 실행 (B-3에서 이미 /home/ubuntu/ddoksori/ 생성됨)
cd /home/ubuntu/ddoksori
git clone <repo-url> .    # ← 마지막 "." 필수!
```

> **⚠️ 주의:** `.` 없이 `git clone <url>`을 실행하면 `/home/ubuntu/ddoksori/LLM/` 하위에
> 코드가 생성되어 워크플로우 경로(`/home/ubuntu/ddoksori/`)와 불일치합니다.
>
> 만약 이미 잘못 clone한 경우:
> ```bash
> # 잘못된 하위 디렉토리 내용물을 상위로 이동
> shopt -s dotglob
> mv /home/ubuntu/ddoksori/LLM/* /home/ubuntu/ddoksori/
> rmdir /home/ubuntu/ddoksori/LLM
> ```

clone 후 확인:
```bash
ls /home/ubuntu/ddoksori/docker-compose.prod.yml   # 파일이 보여야 정상
```

**Phase B 완료 체크리스트:**
- [ ] EC2 인스턴스 생성 (t3.small, Ubuntu 24.04 LTS)
- [ ] 보안 그룹 설정 (22, 80)
- [ ] 탄력적 IP 할당 및 EC2 연결
- [ ] Docker + Docker Compose 설치
- [ ] EC2 IAM Role 연결 (ECR ReadOnly)
- [ ] `/home/ubuntu/ddoksori/` 디렉토리 + `docker-compose.prod.yml` 배치
- [ ] SSH 접속 테스트 성공

---

### Phase C: 배포 파이프라인 연결

#### C-1. 추가 GitHub Secrets 등록

| Secret Name | 값 | 필수 |
|-------------|---|------|
| `EC2_SSH_KEY` | EC2 키 페어의 `.pem` 파일 내용 전체 | ✅ |
| `OPENAI_API_KEY` | OpenAI API 키 (main 전체 테스트용) | ✅ |
| `DISCORD_WEBHOOK` | Discord 웹훅 URL | 선택 |

> **EC2_SSH_KEY 등록 방법:** `.pem` 파일을 텍스트 편집기로 열어 `-----BEGIN RSA PRIVATE KEY-----`부터 `-----END RSA PRIVATE KEY-----`까지 전체 복사하여 등록.

#### C-2. EC2_HOST 설정 → push (코드 수정)

B-2에서 할당한 탄력적 IP(또는 도메인)를 워크플로우에 반영합니다.

**수정 대상 파일 2개:**

`deploy-staging.yml`:
```yaml
env:
  EC2_HOST: <탄력적IP 또는 staging.ddoksori.com>
```

`deploy-production.yml`:
```yaml
env:
  EC2_HOST: <탄력적IP 또는 ddoksori.com>
```

> **도메인이 없으면** 탄력적 IP를 직접 넣으면 됩니다 (예: `3.35.xxx.xxx`).
> **도메인이 있으면** DNS A 레코드를 탄력적 IP로 연결 후 도메인을 입력합니다.

수정 후 commit & push합니다.

#### C-3. Staging 배포 테스트

1. main 브랜치에 코드 머지
2. `build.yml` 성공 → `deploy-staging.yml` 자동 실행
3. GitHub Actions 탭에서 배포 로그 확인
4. `http://<탄력적IP>/health` 접속하여 헬스체크 확인 (Nginx가 Backend로 프록시)
5. `http://<탄력적IP>` 접속하여 Frontend 확인

#### C-4. Production 배포 테스트

1. **GitHub → Settings → Environments → production** 환경 생성
   - Protection rules: "Required reviewers" 설정 (수동 승인)
2. 태그 생성:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. `build.yml` 완료 대기 → `deploy-production.yml` 실행
4. GitHub에서 수동 승인 → 배포 진행
5. 실패 시 자동 롤백 잡 실행 확인

**Phase C 완료 체크리스트:**
- [ ] GitHub Secrets: `EC2_SSH_KEY`, `OPENAI_API_KEY` 등록
- [ ] deploy-staging.yml 내 EC2_HOST 실제 값으로 설정
- [ ] main 머지 → staging 자동 배포 성공
- [ ] 헬스체크 (`/health`) 정상 응답
- [ ] GitHub Environments: production 환경 + 수동 승인 설정
- [ ] v* 태그 → production 배포 테스트 성공
- [ ] (선택) Discord 알림 수신 확인

---

### 전체 진행 상태 추적

| 단계 | 항목 | 상태 |
|------|------|------|
| **A-1** | AWS CLI v2 설치 | ✅ 완료 |
| **A-2** | OIDC Identity Provider 생성 | ✅ 완료 |
| **A-3** | IAM Role 생성 | ✅ 완료 |
| **A-4** | ECR 리포지토리 생성 | ✅ 완료 |
| **A-5** | GitHub Secrets: AWS_ROLE_ARN | ✅ 완료 |
| **A-6** | 워크플로우 파일 확인 | ⬜ 미진행 |
| **A-7** | CI + 빌드 검증 | ⬜ 미진행 |
| **B-1** | EC2 인스턴스 생성 | ⬜ 미진행 |
| **B-2** | 탄력적 IP 할당 | ⬜ 미진행 |
| **B-3** | EC2 초기 설정 | ⬜ 미진행 |
| **B-4** | EC2 IAM Role 연결 | ⬜ 미진행 |
| **B-5** | docker-compose.prod.yml 배치 | ⬜ 미진행 |
| **C-1** | 추가 GitHub Secrets 등록 | ⬜ 미진행 |
| **C-2** | 배포 워크플로우 확인 | ⬜ 미진행 |
| **C-3** | Staging 배포 테스트 | ⬜ 미진행 |
| **C-4** | Production 배포 테스트 | ⬜ 미진행 |

---

## Step 1: CI 기본 (Lint & Test)

### 1.1 Lint Workflow (`.github/workflows/lint.yml`) - 구현 완료

**트리거**: PR 생성, Push to main

**작업**:
- Backend: `black --check`, `isort --check`
- Frontend: `npm run lint` (ESLint)

```yaml
name: Lint

on:
  pull_request:
  push:
    branches: [main]

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install black isort
      - run: black --check backend/
      - run: isort --check-only backend/

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
```

### 1.2 Test Workflow (`.github/workflows/test.yml`) - 구현 완료

**트리거**: PR 생성, Push to main

**서비스**: PostgreSQL (pgvector:pg16) + Redis 7-alpine (3계층 캐싱용)

**테스트 전략**:
- PR 시: `pytest -m "not skip_ci and not llm"` (빠른 피드백, LLM/skip_ci 제외)
- main 머지 시: `pytest -m "not skip_ci"` (전체 테스트, LLM 포함)

**활용 마커** (16개): `unit`, `integration`, `api`, `supervisor`, `agent`, `retrieval`, `generation`, `review`, `slow`, `docker`, `skip_ci`, `llm`, `e2e`, `needs_db`, `needs_data`, `asyncio`

```yaml
name: Test

on:
  pull_request:
  push:
    branches: [main]

env:
  PYTHONPATH: backend

jobs:
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: ddoksori_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r backend/requirements.txt

      - name: Run tests (PR - fast)
        if: github.event_name == 'pull_request'
        run: pytest -c backend/pytest.ini -m "not skip_ci and not llm" backend/scripts/testing -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/ddoksori_test
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          ENABLE_ANSWER_CACHE: false

      - name: Run tests (main - full)
        if: github.ref == 'refs/heads/main'
        run: pytest -c backend/pytest.ini -m "not skip_ci" backend/scripts/testing -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/ddoksori_test
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          ENABLE_ANSWER_CACHE: true
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

**테스트 마커 참고 (16개):**

```bash
# CI에서 사용할 마커 조합
pytest -m "not skip_ci"              # skip_ci 제외한 모든 테스트
pytest -m "not skip_ci and not llm"  # LLM API 호출 제외 (빠른 테스트)
pytest -m "unit"                     # 유닛 테스트만
pytest -m "integration"              # DB 필요 테스트
pytest -m "e2e"                      # E2E 테스트

# 전체 마커 목록 (pytest.ini)
# unit, integration, api, supervisor, agent, retrieval, generation, review,
# slow, docker, skip_ci, llm, e2e, needs_db, needs_data, asyncio
```

### 1.3 Dockerfile 프로덕션화 - 구현 완료

**개발 Dockerfile** (`backend/Dockerfile`, `frontend/Dockerfile`)은 `--reload`/`npm run dev` 모드로 개발 목적 전용.

**프로덕션 Dockerfile**은 별도 파일로 구현 완료:

#### `backend/Dockerfile.prod` - 구현 완료

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy requirements first for layer caching
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY utils/ ./utils/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server (gunicorn + uvicorn workers)
EXPOSE 8000
CMD ["sh", "-c", "gunicorn app.main:app \
    -w ${WEB_CONCURRENCY:-4} \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile -"]
```

> **Note:** `WEB_CONCURRENCY` 환경변수로 워커 수 동적 조정 가능 (기본 4). `--timeout 120`은 LLM API 호출 대기, `--graceful-timeout 30`은 안전한 종료 대기. `utils/` 디렉토리도 복사됨.

#### `frontend/Dockerfile.prod` - 구현 완료

```dockerfile
# Build stage
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### `frontend/nginx.conf` - 구현 완료

SSE 스트리밍, gzip 압축, 7개 백엔드 프록시, 정적 파일 캐싱 포함:

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # SSE streaming support (must be before /chat to take priority)
    location /chat/stream {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
    }

    # API proxy - backend endpoints
    location /chat {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /search {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /auth {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /case {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /metrics {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://backend:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Static file caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## Step 2: Docker 이미지 빌드 & ECR 푸시

### 2.1 Build Workflow (`.github/workflows/build.yml`) - 구현 완료

**트리거**: Push to main, Tag 생성 (`v*`)

**작업**:
- Docker Buildx로 Backend/Frontend 이미지 빌드
- `docker/metadata-action@v5`으로 태그 자동 관리 (latest, sha-, semver)
- GHA 캐시로 빌드 레이어 캐싱 (`cache-from: type=gha`, `cache-to: type=gha,mode=max`)
- AWS ECR에 이미지 푸시

> **Note:** ECR Registry URL은 GitHub Secret이 아닌, `aws-actions/amazon-ecr-login@v2` 스텝의
> output (`steps.login-ecr.outputs.registry`)에서 동적으로 획득합니다.

```yaml
name: Build and Push

on:
  push:
    branches: [main]
    tags: ['v*']

env:
  AWS_REGION: ap-northeast-2
  ECR_BACKEND: ddoksori-backend
  ECR_FRONTEND: ddoksori-frontend

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Extract metadata for backend
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_BACKEND }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=semver,pattern={{version}}

      - name: Extract metadata for frontend
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_FRONTEND }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=semver,pattern={{version}}

      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          file: ./backend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 2.2 AWS ECR 설정 (사전 작업)

> ECR 리포지토리 생성 및 OIDC 설정은 **Step 0: Phase A**를 참조하세요.

---

## Step 3: Staging 배포

### 3.1 Deploy Staging Workflow (`.github/workflows/deploy-staging.yml`) - 구현 완료

**트리거**: Build and Push 워크플로우 성공 완료 시 (main 브랜치)

**주요 특징**:
- ECR 로그인 스텝 분리 (`aws-actions/amazon-ecr-login@v2`)
- `--remove-orphans`로 고아 컨테이너 정리
- `docker image prune -f`로 이전 이미지 정리
- 5회 재시도 헬스체크 (초기 30초 대기 + 10초 간격)
- Success/Failure 별도 Discord 알림

```yaml
name: Deploy to Staging

on:
  workflow_run:
    workflows: ["Build and Push"]
    types: [completed]
    branches: [main]

env:
  AWS_REGION: ap-northeast-2
  EC2_HOST: staging.ddoksori.com

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Deploy to Staging
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ubuntu/ddoksori

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Pull latest images
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            docker compose -f docker-compose.prod.yml pull

            # Deploy with zero-downtime
            docker compose -f docker-compose.prod.yml up -d --remove-orphans

            # Cleanup old images
            docker image prune -f

            # Show status
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          echo "Waiting for services to start..."
          sleep 30

          # Backend health check
          for i in {1..5}; do
            if curl -sf http://${{ env.EC2_HOST }}:8000/health; then
              echo "Backend is healthy!"
              break
            fi
            echo "Attempt $i failed, retrying in 10s..."
            sleep 10
          done

          # Final verification
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification - Success
        if: success()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: success
          title: "Staging Deployment"
          description: |
            **Status**: Success
            **Commit**: `${{ github.event.workflow_run.head_sha }}`
            **Branch**: main
            **URL**: http://${{ env.EC2_HOST }}

      - name: Discord Notification - Failure
        if: failure()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: failure
          title: "Staging Deployment"
          description: |
            **Status**: Failed
            **Commit**: `${{ github.event.workflow_run.head_sha }}`
            **Branch**: main

            Check GitHub Actions for details.
```

### 3.2 Production Compose File (`docker-compose.prod.yml`) - 구현 완료

AWS Secrets Manager 통합, MAS 에이전트 설정, 임베딩 설정, Redis 메모리 제한, 커스텀 네트워크 포함:

```yaml
services:
  backend:
    image: ${ECR_REGISTRY}/ddoksori-backend:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "8000:8000"
    environment:
      # === AWS Secrets Manager ===
      - USE_AWS_SECRETS=${USE_AWS_SECRETS:-false}
      - SECRETS_ENV=${SECRETS_ENV:-staging}
      - AWS_DEFAULT_REGION=ap-northeast-2

      # === Database (비-시크릿만, 시크릿은 Secrets Manager) ===
      - DB_POOL_SIZE=${DB_POOL_SIZE:-5}
      - DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-10}
      - DATABASE_URL=${DATABASE_URL:-}

      # === Redis (3-tier caching) ===
      - REDIS_HOST=${REDIS_HOST:-redis}
      - REDIS_PORT=${REDIS_PORT:-6379}
      - ENABLE_ANSWER_CACHE=${ENABLE_ANSWER_CACHE:-true}

      # === LLM API Keys ===
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}

      # === MAS Supervisor Settings ===
      - MODEL_SUPERVISOR=${MODEL_SUPERVISOR:-gpt-4o}
      - MODEL_DRAFT_AGENT=${MODEL_DRAFT_AGENT:-gpt-4o}
      - MODEL_REVIEW_AGENT=${MODEL_REVIEW_AGENT:-gpt-4o}

      # === Embedding ===
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-large}
      - USE_OPENAI_EMBEDDING=${USE_OPENAI_EMBEDDING:-true}

      # === Agent Tuning ===
      - SIMILARITY_THRESHOLD=${SIMILARITY_THRESHOLD:-0.55}
      - MAX_SUPERVISOR_ITERATIONS=${MAX_SUPERVISOR_ITERATIONS:-10}

      # === Logging ===
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - ddoksori-net

  frontend:
    image: ${ECR_REGISTRY}/ddoksori-frontend:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "80:80"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - ddoksori-net

  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ddoksori-net

networks:
  ddoksori-net:
    driver: bridge

volumes:
  redis-data:
```

### 3.3 AWS Secrets Manager 통합 - 구현 완료

프로덕션 시크릿 관리를 `.env` 파일에서 AWS Secrets Manager로 전환.
(상세 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`)

| 항목 | 기존 | 변경 후 | 이유 |
|------|------|---------|------|
| **시크릿 저장** | `.env` 파일 | AWS Secrets Manager | 자동 로테이션, 감사 로그, IAM 접근 제어 |
| **시크릿 로딩** | Pydantic Settings dotenv | `inject_aws_secrets()` → os.environ 주입 | 기존 코드 최소 변경 |
| **docker-compose.prod.yml** | 시크릿 직접 환경변수 | `USE_AWS_SECRETS=true` + Secrets Manager | EC2에 .env 관리 불필요 |
| **비용** | 무료 | ~$6/월 | 7개 시크릿 x 2환경 |

**구현 완료 파일:**
- `backend/app/common/secrets.py` - AWS Secrets Manager SDK 래퍼, os.environ 사전 주입
  - SECRET_CATEGORIES (라인 27-35): database, llm, oauth/google, oauth/naver, security, infra
  - `inject_aws_secrets()` → `get_config()` 호출 전에 환경변수 주입

**환경별 시크릿 흐름:**

```
로컬 개발:  .env → Pydantic Settings (변경 없음)
CI/CD:      GitHub Secrets → 환경변수 (변경 없음)
Staging:    EC2 IAM Role → Secrets Manager → os.environ → Pydantic Settings
Production: EC2 IAM Role → Secrets Manager → os.environ → Pydantic Settings
```

---

## Step 4: Production 배포

### 4.1 Deploy Production Workflow (`.github/workflows/deploy-production.yml`) - 구현 완료

**트리거**: `v*` 태그 생성 시

**주요 특징**:
- `wait-for-build` 잡: Build 워크플로우 완료 대기 (`lewagon/wait-on-check-action@v1.3.4`)
- `environment: production`: GitHub 수동 승인 필요
- `backups/` 디렉토리에 배포 전 백업 생성
- 10회 재시도 헬스체크 (초기 30초 대기 + 15초 간격)
- Success/Failure 별도 Discord 알림 (색상 코드)
- **자동 롤백 잡**: 배포 실패 시 `production-rollback` environment로 자동 롤백

```yaml
name: Deploy to Production

on:
  push:
    tags: ['v*']

env:
  AWS_REGION: ap-northeast-2
  EC2_HOST: ddoksori.com

jobs:
  # Wait for build to complete first
  wait-for-build:
    runs-on: ubuntu-latest
    steps:
      - name: Wait for Build workflow
        uses: lewagon/wait-on-check-action@v1.3.4
        with:
          ref: ${{ github.ref }}
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          check-name: build-and-push
          wait-interval: 30

  deploy:
    runs-on: ubuntu-latest
    needs: wait-for-build
    environment: production  # Requires manual approval in GitHub settings
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Get version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Deploy to Production
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ubuntu/ddoksori

            # Backup current deployment
            echo "Creating backup..."
            docker compose -f docker-compose.prod.yml config > backups/backup-$(date +%Y%m%d-%H%M%S).yml 2>/dev/null || true
            mkdir -p backups

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Pull new version with specific tag
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            export IMAGE_TAG=${{ steps.version.outputs.VERSION }}
            docker compose -f docker-compose.prod.yml pull

            # Rolling update
            echo "Deploying version $IMAGE_TAG..."
            docker compose -f docker-compose.prod.yml up -d --remove-orphans

            # Cleanup old images (keep last 3)
            docker image prune -f

            # Show status
            echo "Deployment complete:"
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          echo "Waiting for services to start..."
          sleep 30

          # Backend health check with retries
          for i in {1..10}; do
            if curl -sf http://${{ env.EC2_HOST }}:8000/health; then
              echo "Backend is healthy!"
              break
            fi
            echo "Attempt $i failed, retrying in 15s..."
            sleep 15
          done

          # Final verification
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification - Success
        if: success()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: success
          title: "Production Deployment"
          color: 0x00ff00
          description: |
            **Status**: Success
            **Version**: `${{ steps.version.outputs.VERSION }}`
            **Commit**: `${{ github.sha }}`
            **URL**: http://${{ env.EC2_HOST }}

            Production deployment completed successfully!

      - name: Discord Notification - Failure
        if: failure()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: failure
          title: "Production Deployment Failed"
          color: 0xff0000
          description: |
            **Status**: Failed
            **Version**: `${{ steps.version.outputs.VERSION }}`
            **Commit**: `${{ github.sha }}`

            Manual intervention may be required.
            Consider rolling back to previous version.

  # Automatic rollback on deploy failure
  rollback:
    runs-on: ubuntu-latest
    if: failure() && needs.deploy.result == 'failure'
    needs: deploy
    environment: production-rollback
    permissions:
      id-token: write
      contents: read

    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Rollback to previous version
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ubuntu/ddoksori

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Rollback to latest (previous stable)
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            export IMAGE_TAG=latest
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d

            echo "Rolled back to latest stable version"
            docker compose -f docker-compose.prod.yml ps

      - name: Discord Notification - Rollback
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: ${{ job.status }}
          title: "Production Rollback"
          description: |
            **Status**: ${{ job.status }}
            **Action**: Rolled back to previous stable version

            Please investigate the failed deployment.
```

### 4.2 Rollback 절차

배포 실패 시 **자동 롤백 잡**이 먼저 실행됩니다. 자동 롤백도 실패하거나 수동 롤백이 필요한 경우:

```bash
# EC2에서 수동 롤백
cd /home/ubuntu/ddoksori

# 이전 이미지로 롤백
export IMAGE_TAG=v1.0.0  # 이전 버전
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 또는 백업된 설정 사용
docker compose -f backups/backup-YYYYMMDD-HHMMSS.yml up -d
```

---

## Step 5: DB 백업 자동화

### 5.1 Weekly DB Backup Workflow (`.github/workflows/db-backup.yml`) - 구현 완료

**트리거**: 매주 일요일 04:00 UTC (한국시간 13:00) + 수동 트리거 (`workflow_dispatch`)

**작업**:
- PostgreSQL 데이터베이스를 `pg_dump`로 백업
- S3 버킷 (`ddoksori-backups`)에 업로드
- weekly/monthly/manual 타입 분류
- 실패 시 GitHub Issue 자동 생성 (`bug` + `infrastructure` 라벨)

> **Note:** S3 버킷 리전은 `us-east-1`로, CI/CD의 ECR/EC2 리전(`ap-northeast-2`)과 다릅니다.
> 이는 S3 비용 최적화 및 글로벌 내구성을 위한 의도적 설계입니다.

```yaml
name: Weekly DB Backup

on:
  schedule:
    # 매주 일요일 04:00 UTC (한국시간 13:00)
    - cron: '0 4 * * 0'
  workflow_dispatch:
    inputs:
      backup_type:
        description: 'Backup type (weekly, monthly, manual)'
        required: false
        default: 'weekly'
        type: choice
        options:
          - weekly
          - monthly
          - manual

env:
  S3_BUCKET: ddoksori-backups
  AWS_REGION: us-east-1

jobs:
  backup:
    name: Backup PostgreSQL to S3
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install PostgreSQL client
        run: |
          sudo apt-get update
          sudo apt-get install -y postgresql-client

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Verify S3 bucket access
        run: |
          aws s3 ls s3://${{ env.S3_BUCKET }}/ || echo "Bucket empty or first backup"

      - name: Run backup script
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_NAME: ${{ secrets.DB_NAME }}
          PGPASSWORD: ${{ secrets.DB_PASSWORD }}
          S3_BUCKET: ${{ env.S3_BUCKET }}
        run: |
          chmod +x ./backend/scripts/backup/backup_to_s3.sh
          ./backend/scripts/backup/backup_to_s3.sh ${{ github.event.inputs.backup_type || 'weekly' }}

      - name: List recent backups
        run: |
          echo "=== Recent Weekly Backups ==="
          aws s3 ls s3://${{ env.S3_BUCKET }}/weekly/ --human-readable | tail -5
          echo ""
          echo "=== Recent Monthly Backups ==="
          aws s3 ls s3://${{ env.S3_BUCKET }}/monthly/ --human-readable | tail -5

  notify-on-failure:
    name: Notify on Failure
    runs-on: ubuntu-latest
    needs: backup
    if: failure()

    steps:
      - name: Create failure issue
        uses: actions/github-script@v7
        with:
          script: |
            const title = `DB Backup Failed - ${new Date().toISOString().split('T')[0]}`;
            const body = `
            ## Database Backup Failed

            **Workflow Run:** [${context.runId}](${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId})
            **Triggered By:** ${context.eventName}
            **Time:** ${new Date().toISOString()}

            Please investigate and manually trigger a backup after fixing the issue.

            ### Checklist
            - [ ] Check AWS credentials (expired?)
            - [ ] Check RDS connectivity
            - [ ] Check S3 bucket permissions
            - [ ] Manually run backup after fix
            `;

            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: title,
              body: body,
              labels: ['bug', 'infrastructure']
            });
```

---

## GitHub Secrets 설정

GitHub Repository → Settings → Secrets and variables → Actions

### CI/CD 파이프라인용

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `AWS_ROLE_ARN` | build, deploy-staging, deploy-production, db-backup | AWS OIDC Role ARN (ECR/EC2/S3 접근) |
| `EC2_SSH_KEY` | deploy-staging, deploy-production | EC2 SSH 개인키 |
| `OPENAI_API_KEY` | test | LLM 테스트용 API 키 (main 브랜치 전체 테스트) |
| `DISCORD_WEBHOOK` | deploy-staging, deploy-production | Discord 알림 웹훅 URL |

### DB 백업용

> **Note:** AWS 인증은 OIDC (`AWS_ROLE_ARN`)로 통일됨. 정적 `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`는 더 이상 사용하지 않음.

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `DB_HOST` | db-backup | RDS 호스트 주소 |
| `DB_USER` | db-backup | RDS 사용자명 |
| `DB_NAME` | db-backup | RDS 데이터베이스명 |
| `DB_PASSWORD` | db-backup | RDS 비밀번호 |

### AI 코드리뷰용 (보조 자동화)

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | claude-code-review, claude | Claude Code Action OAuth 토큰 |
| `GOOGLE_GENERATIVE_AI_API_KEY` | opencode | Google Gemini API 키 |
| `GEMINI_API_KEY` | opencode | Gemini API 키 (대체) |

> **Note:** `GITHUB_TOKEN`은 자동 제공되므로 별도 설정 불필요. `ECR_REGISTRY`는 시크릿이 아니라 ECR 로그인 스텝 output에서 동적 획득.

### AWS Secrets Manager (EC2 런타임용, GitHub Secrets 아님)

> 아래는 EC2에서 런타임에 로드되는 AWS Secrets Manager 경로입니다.
> 소스: `backend/app/common/secrets.py` (SECRET_CATEGORIES, 라인 27-35)

| Secret Path | 주입되는 환경변수 |
|-------------|-------------------|
| `ddoksori/{env}/database` | DB_HOST, DB_USER, DB_PASSWORD, DATABASE_URL |
| `ddoksori/{env}/llm` | OPENAI_API_KEY, ANTHROPIC_API_KEY |
| `ddoksori/{env}/oauth/google` | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET |
| `ddoksori/{env}/oauth/naver` | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET |
| `ddoksori/{env}/security` | JWT_SECRET_KEY, SECRET_KEY |
| `ddoksori/{env}/infra` | HF_TOKEN, EXAONE_RUNPOD_API_KEY |

---

## 구현 완료 파일 목록

### CI/CD 핵심 파일

| 파일 | 설명 | 상태 |
|------|------|------|
| `.github/workflows/lint.yml` | Lint 워크플로우 | 구현 완료 |
| `.github/workflows/test.yml` | 테스트 워크플로우 | 구현 완료 |
| `.github/workflows/build.yml` | 이미지 빌드 워크플로우 (Buildx + GHA 캐시) | 구현 완료 |
| `.github/workflows/deploy-staging.yml` | Staging 배포 워크플로우 | 구현 완료 |
| `.github/workflows/deploy-production.yml` | Production 배포 + 자동 롤백 | 구현 완료 |
| `.github/workflows/db-backup.yml` | Weekly DB 백업 → S3 | 구현 완료 |
| `backend/Dockerfile.prod` | 프로덕션용 Backend Dockerfile | 구현 완료 |
| `frontend/Dockerfile.prod` | 프로덕션용 Frontend Dockerfile | 구현 완료 |
| `frontend/nginx.conf` | Nginx 설정 (SSE, gzip, 프록시) | 구현 완료 |
| `docker-compose.prod.yml` | 프로덕션 Compose 파일 | 구현 완료 |
| `backend/app/common/secrets.py` | AWS Secrets Manager SDK 래퍼 | 구현 완료 |

### 보조 자동화 (CI/CD 파이프라인 외)

| 파일 | 설명 |
|------|------|
| `.github/workflows/claude-code-review.yml` | Claude Code PR 자동 리뷰 |
| `.github/workflows/claude.yml` | Claude Code Action |
| `.github/workflows/opencode.yml` | OpenCode (Gemini) Action |

---

## 운영 가이드

| 작업 | 트리거 | 자동화 |
|------|--------|--------|
| 코드 린트 | PR 생성/Push to main | 자동 |
| 테스트 실행 | PR 생성/Push to main | 자동 |
| Docker 이미지 빌드 | Push to main / Tag 생성 | 자동 |
| Staging 배포 | main 머지 후 Build 성공 | 자동 |
| Production 배포 | v* 태그 생성 | 자동 (수동 승인) |
| DB 백업 | 매주 일요일 13:00 KST | 자동 |
| Production 롤백 | 배포 실패 시 | 자동 (수동 트리거 가능) |

---

## 비용 참고 (AWS)

아카이브된 비용 분석 (`docs/_archive/plans/deploy/02_cost_analysis.md`) 기준:
- EC2 t3.small: ~$15/월
- RDS db.t3.micro: ~$15/월
- ECR: ~$1/월 (스토리지)
- S3 (DB 백업): ~$1/월
- Secrets Manager: ~$6/월 (7개 시크릿 x 2환경)
- **예상 총 비용**: $30-70/월

> **EC2 인스턴스 검토 (2026-02-01):** t3.small (2GB RAM)에서 gunicorn 4 워커 + Redis 256MB + Nginx를
> 실행하면 메모리가 빡빡합니다 (~2.2GB 추정). 초기 운영 시 `WEB_CONCURRENCY=2`로 워커를 줄이거나,
> t3.medium (4GB, ~$30/월)으로 업그레이드를 권장합니다.

---

## Step 6: 도메인 + HTTPS 적용

> **Status**: 도메인 구매 전 검토 완료 (2026-02-03)
>
> **결론**: EC2 + Nginx + Let's Encrypt 방식으로 진행 (ALB 불필요)

### 6.0 ALB 도입 검토

| 항목 | ALB 방식 | EC2 직접 (Nginx + Let's Encrypt) |
|------|---------|-------------------------------|
| SSL 인증서 | ACM 무료 (자동갱신) | Let's Encrypt 무료 (90일 자동갱신) |
| 로드밸런서 | **~$24-38/월** (고정비) | **$0** (Nginx가 대신) |
| EC2 | ~$15/월 | ~$15/월 |
| **월 총액** | **~$59-73/월** | **~$35/월** |

**판단: 현재 단계에서 ALB 불필요**

- EC2 1대 → 로드밸런싱 대상 없음
- ALB 고정비 ~$24/월 → 예산($30-70/월)의 절반 소진
- SSE 스트리밍 시 ALB idle timeout 추가 설정 필요 (기본 60초로 끊김)
- ALB 도입 시점: EC2 2대+, 동시접속 1,000+, 월 $100+ 예산

### 6.1 도메인 구매 (AWS Route 53 권장)

**Route 53 권장 이유**: DNS 레코드를 AWS 콘솔에서 직접 관리, 네임서버 변경 불필요

```
1. AWS Console → Route 53 → Registered domains → Register Domain
2. 도메인 검색 (예: ddoksori.com) → 선택 → 결제 (~$13/년)
   - Privacy Protection: "Enable" (WHOIS 비공개)
   - 등록 완료까지 보통 15분~1시간 (최대 3일)
3. 이메일 인증 링크 클릭 (15일 내 미확인 시 도메인 정지)
4. Hosted Zone (자동 생성됨) → Create Record:
   - A 레코드: (비워둠) → 13.209.245.44 (탄력적 IP)
   - CNAME: www → ddoksori.com
5. DNS 전파 확인: nslookup ddoksori.com → 13.209.245.44 나오면 성공
```

> **Note**: 탄력적 IP는 그대로 유지. 도메인은 탄력적 IP를 가리키는 별칭일 뿐.
> 향후 서버 분리 시: `staging.ddoksori.com` → staging IP, `ddoksori.com` → production IP

### 6.2 EC2 보안 그룹 변경

443 포트 추가 필요:

```
EC2 Console → 인스턴스 → Security 탭 → 보안 그룹 클릭
  → Edit inbound rules → Add rule:
    Type: HTTPS, Port: 443, Source: 0.0.0.0/0
```

최종 인바운드:

| 포트 | 소스 | 용도 |
|------|------|------|
| 22 | My IP | SSH |
| 80 | 0.0.0.0/0 | HTTP → HTTPS 리다이렉트 |
| **443** | **0.0.0.0/0** | **HTTPS** |

### 6.3 HTTPS 적용 (Let's Encrypt + Certbot)

**아키텍처 변경:**

```
변경 전: 사용자 → http://<IP>:80 → Nginx → Backend:8000
변경 후: 사용자 → https://ddoksori.com:443 → Nginx (SSL 종료) → Backend:8000
                  http://ddoksori.com:80  → 301 리다이렉트 → https://...
```

#### docker-compose.prod.yml 변경

```yaml
services:
  frontend:
    # ... 기존 설정 유지 ...
    ports:
      - "80:80"
      - "443:443"    # 추가
    volumes:
      - certbot-etc:/etc/letsencrypt        # 추가
      - certbot-var:/var/lib/letsencrypt    # 추가
      - certbot-www:/var/www/certbot        # 추가

  certbot:    # 새 서비스
    image: certbot/certbot:latest
    volumes:
      - certbot-etc:/etc/letsencrypt
      - certbot-var:/var/lib/letsencrypt
      - certbot-www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done'"
    networks:
      - ddoksori-net

volumes:
  redis-data:
  certbot-etc:    # 추가
  certbot-var:    # 추가
  certbot-www:    # 추가
```

#### frontend/nginx.conf 변경

HTTP→HTTPS 리다이렉트 + SSL 서버 블록 추가:

```nginx
# HTTP → HTTPS 리다이렉트
server {
    listen 80;
    server_name ddoksori.com www.ddoksori.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 메인 서버
server {
    listen 443 ssl;
    server_name ddoksori.com www.ddoksori.com;
    root /usr/share/nginx/html;
    index index.html;

    ssl_certificate /etc/letsencrypt/live/ddoksori.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ddoksori.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    add_header Strict-Transport-Security "max-age=15768000; includeSubDomains" always;

    # 기존 gzip, SPA routing, API proxy, SSE streaming, static caching 설정 동일
    # SSE에 proxy_read_timeout 3600s 추가
}
```

#### frontend/Dockerfile.prod 변경

```dockerfile
# Production stage에 추가:
RUN mkdir -p /var/www/certbot
EXPOSE 80 443    # 443 추가
```

#### 최초 인증서 발급 (EC2에서 1회 수동)

DNS 전파 확인 후 EC2에서 실행:

```bash
# 1) 기존 컨테이너 중지
cd /home/ubuntu/ddoksori
docker compose -f docker-compose.prod.yml down

# 2) certbot standalone으로 인증서 발급
docker run --rm -p 80:80 \
  -v certbot-etc:/etc/letsencrypt \
  -v certbot-var:/var/lib/letsencrypt \
  certbot/certbot certonly --standalone \
    --email <이메일> --agree-tos --no-eff-email \
    -d ddoksori.com -d www.ddoksori.com

# 3) 발급 확인
docker run --rm -v certbot-etc:/etc/letsencrypt \
  alpine ls /etc/letsencrypt/live/ddoksori.com/
# → fullchain.pem, privkey.pem 등 확인

# 4) 전체 서비스 시작
export ECR_REGISTRY=<ECR URL>
docker compose -f docker-compose.prod.yml up -d
```

#### 인증서 자동 갱신

certbot 컨테이너가 12시간마다 갱신 시도. EC2 crontab에 nginx 리로드 추가:

```bash
# 매월 1일, 15일 자정에 nginx 리로드
0 0 1,15 * * cd /home/ubuntu/ddoksori && docker compose -f docker-compose.prod.yml exec -T frontend nginx -s reload 2>/dev/null
```

### 6.4 CI/CD 워크플로우 변경

**deploy-staging.yml / deploy-production.yml 공통:**

```yaml
# 변경 전:
env:
  EC2_HOST: 13.209.245.44

# 변경 후:
env:
  EC2_HOST: ddoksori.com

# 헬스체크 변경:
#   http://${{ env.EC2_HOST }}:8000/health
# → https://${{ env.EC2_HOST }}/health
```

> Nginx가 443에서 SSL 처리 후 backend:8000으로 프록시하므로 외부에서는 443(https 기본)으로 접근.

### 6.5 OAuth 콜백 URL 업데이트

| 서비스 | 변경 전 | 변경 후 |
|--------|---------|---------|
| Google OAuth | `http://13.209.245.44/auth/google/callback` | `https://ddoksori.com/auth/google/callback` |
| Naver OAuth | `http://13.209.245.44/auth/naver/callback` | `https://ddoksori.com/auth/naver/callback` |

### 6.6 적합성 검토 결과: 적합

| 항목 | 탄력적 IP만 | 도메인 + HTTPS |
|------|------------|---------------|
| 사용자 접근성 | IP 직접 입력 | ddoksori.com |
| HTTPS | 자체서명만 가능 | Let's Encrypt 무료 |
| OAuth 콜백 | 일부 제공자 제한 | 표준 지원 |
| 브라우저 경고 | "안전하지 않음" 표시 | 자물쇠 아이콘 |
| 서버 이전 | IP 변경 시 전체 수정 | DNS만 변경 |
| 비용 | 무료 | ~$13/년 |

### 6.7 구현 순서

| Phase | 작업 | 위치 |
|-------|------|------|
| **1. 도메인** | Route 53 구매 → A/CNAME 레코드 → DNS 전파 확인 | AWS 콘솔 |
| **2. 보안+코드** | 443 포트 추가, docker-compose/nginx/Dockerfile 수정 | AWS 콘솔 + 코드 |
| **3. 인증서** | 코드 배포 → EC2에서 certbot 인증서 발급 | EC2 |
| **4. CI/CD** | deploy-staging/production.yml EC2_HOST, 헬스체크 변경 | 코드 |
| **5. OAuth+검증** | Google/Naver 콜백 URL 변경 → 전체 테스트 | 외부 + 브라우저 |

### 6.8 변경 대상 파일

| 파일 | 변경 유형 |
|------|----------|
| `docker-compose.prod.yml` | certbot 서비스/볼륨, frontend 443 포트 |
| `frontend/nginx.conf` | HTTPS 서버 블록, HTTP 리다이렉트, SSL |
| `frontend/Dockerfile.prod` | EXPOSE 443, /var/www/certbot |
| `.github/workflows/deploy-staging.yml` | EC2_HOST → 도메인, 헬스체크 https |
| `.github/workflows/deploy-production.yml` | EC2_HOST → 도메인, 헬스체크 https |

## Step 7: AWS 리소스 정리 (서비스 해제)

> **Status**: 가이드 작성 완료 (2026-02-03)
>
> 서비스 운영 종료 시 도메인 등록을 **제외한** 모든 AWS 리소스를 안전하게 해제하는 절차.
> 과금이 발생하는 리소스를 빠짐없이 정리하여 불필요한 비용을 방지합니다.

### 7.0 정리 대상 리소스 요약

| 순서 | 서비스 | 리소스 | 월 비용 | 정리 방법 |
|------|--------|--------|---------|-----------|
| 1 | EC2 | 인스턴스 (t3.small) | ~$15 | Terminate |
| 2 | EC2 | 탄력적 IP | 미연결 시 $3.65 | Release |
| 3 | RDS | DB 인스턴스 (db.t3.micro) | ~$15 | Delete |
| 4 | Secrets Manager | 12개 시크릿 | ~$6 | Delete |
| 5 | S3 | ddoksori-backups 버킷 | ~$1 | 객체 삭제 → 버킷 삭제 |
| 6 | ECR | 2개 리포지토리 | ~$1 | 이미지 삭제 → 리포 삭제 |
| 7 | Route 53 | Hosted Zone | $0.50 | 커스텀 레코드 삭제 → Zone 삭제 |
| 8 | Route 53 | 도메인 자동갱신 | $13/년 | Disable (도메인 유지) |
| 9 | IAM | Role, Policy, OIDC | 무료 | 정리 권장 |
| 10 | EC2 | 보안 그룹, 키 페어 | 무료 | 정리 권장 |

> **정리 완료 시 절감 비용**: ~$38-40/월 (연간 ~$460)

### 7.1 EC2 인스턴스 종료 (Terminate)

> ⚠️ **Terminate = 영구 삭제**. Stop과 다르며 복구 불가. EBS 볼륨도 함께 삭제됩니다.

```
1. EC2 Console → Instances → 대상 인스턴스 선택
2. Instance state → Stop instance (먼저 안전하게 중지)
   - 중지 완료 확인 (State: Stopped)
3. 필요한 데이터가 있다면 이 시점에 백업:
   - EC2 → 인스턴스 선택 → Actions → Image and templates → Create image (AMI)
   - 또는 SSH로 접속하여 파일 다운로드
4. Instance state → Terminate instance
5. 확인 팝업에서 "Terminate" 클릭
6. State가 "Terminated"로 변경되면 완료 (몇 분 후 목록에서 사라짐)
```

### 7.2 탄력적 IP 해제 (Release)

> ⚠️ EC2 인스턴스에 연결되지 않은 탄력적 IP는 **시간당 $0.005** 과금됩니다.
> 반드시 EC2 Terminate 후에 해제하세요.

```
1. EC2 Console → Network & Security → Elastic IPs
2. 대상 IP (13.209.245.44) 선택
3. Actions → Release Elastic IP address
4. 확인 팝업에서 "Release" 클릭
5. 목록에서 사라지면 완료
```

> **Note**: 해제된 IP는 다시 돌아오지 않습니다. 같은 IP가 필요하면 Release하지 마세요.

### 7.3 RDS 인스턴스 삭제

> 💡 삭제 전 최종 스냅샷 생성을 권장합니다 (무료, 필요 시 복원 가능).

```
1. RDS Console → Databases → 대상 DB 인스턴스 선택
2. Actions → Delete
3. 삭제 옵션:
   - ✅ Create final snapshot: "ddoksori-final-YYYYMMDD" (권장)
   - ⬜ Retain automated backups: 체크 해제 (과금 방지)
   - 확인란에 "delete me" 입력
4. "Delete" 클릭
5. Status가 "Deleting" → 목록에서 사라지면 완료 (수 분 소요)
```

**스냅샷 정리** (더 이상 DB가 필요 없을 때):

```
1. RDS Console → Snapshots
2. 불필요한 스냅샷 선택 → Actions → Delete snapshot
   - 스냅샷 보관 시 과금: ~$0.02/GB/월
```

### 7.4 Secrets Manager 시크릿 삭제

> 기본 복구 기간은 7일이며, 즉시 삭제도 가능합니다.

DDOKSORI에서 사용하는 시크릿 경로 (총 12개):

| 환경 | 시크릿 경로 |
|------|------------|
| staging | `ddoksori/staging/database`, `ddoksori/staging/llm`, `ddoksori/staging/oauth/google`, `ddoksori/staging/oauth/naver`, `ddoksori/staging/security`, `ddoksori/staging/infra` |
| production | `ddoksori/production/database`, `ddoksori/production/llm`, `ddoksori/production/oauth/google`, `ddoksori/production/oauth/naver`, `ddoksori/production/security`, `ddoksori/production/infra` |

```
1. Secrets Manager Console → Secrets
2. 각 시크릿 클릭 → Actions → Delete secret
3. 복구 기간 선택:
   - 기본: 7일 (7일 내 복원 가능)
   - 즉시 삭제: "Schedule deletion without a waiting period" 체크
4. "Schedule deletion" 클릭
5. 12개 시크릿 모두 반복
```

> **AWS CLI로 일괄 삭제** (빠른 방법):
> ```bash
> # 7일 복구 기간
> for secret in database llm oauth/google oauth/naver security infra; do
>   for env in staging production; do
>     aws secretsmanager delete-secret \
>       --secret-id "ddoksori/$env/$secret" \
>       --recovery-window-in-days 7 \
>       --region ap-northeast-2
>   done
> done
>
> # 즉시 삭제 (복구 불가)
> # --recovery-window-in-days 7 대신 --force-delete-without-recovery 사용
> ```

### 7.5 S3 버킷 삭제

> S3 버킷은 비어 있어야 삭제할 수 있습니다.

```
1. S3 Console → Buckets → "ddoksori-backups" 클릭
2. 버킷 비우기:
   - "Empty" 버튼 클릭
   - 확인란에 "permanently delete" 입력 → "Empty" 클릭
   - 모든 객체 삭제 완료 대기
3. 버킷 삭제:
   - Buckets 목록으로 돌아가기
   - "ddoksori-backups" 선택 → "Delete" 클릭
   - 확인란에 버킷 이름 입력 → "Delete bucket" 클릭
```

> **Note**: S3 버킷 이름은 글로벌 고유. 삭제 후 같은 이름으로 즉시 재생성 불가할 수 있음.

### 7.6 ECR 리포지토리 삭제

DDOKSORI ECR 리포지토리 2개: `ddoksori-backend`, `ddoksori-frontend`

```
1. ECR Console → Repositories
2. "ddoksori-backend" 선택 → Delete
   - 확인란에 "delete" 입력 → "Delete" 클릭
3. "ddoksori-frontend" 선택 → Delete
   - 확인란에 "delete" 입력 → "Delete" 클릭
```

> **Note**: 리포지토리 삭제 시 내부 이미지도 모두 삭제됩니다. 별도로 이미지를 먼저 삭제할 필요 없음.

### 7.7 Route 53 정리 (도메인은 유지)

> 도메인 등록은 유지하되, Hosted Zone과 커스텀 레코드를 삭제하여 $0.50/월 비용 절감.

#### Hosted Zone 레코드 삭제

```
1. Route 53 Console → Hosted zones → ddoksori.com 클릭
2. 커스텀 레코드 삭제 (A, CNAME 등):
   - A 레코드 (ddoksori.com → 13.209.245.44) 선택 → Delete
   - CNAME 레코드 (www → ddoksori.com) 선택 → Delete
   - ⚠️ NS 레코드, SOA 레코드는 삭제하지 마세요 (Zone 삭제 시 자동 제거)
3. 커스텀 레코드가 모두 삭제되었는지 확인
```

#### Hosted Zone 삭제

```
1. Hosted zones 목록으로 돌아가기
2. "ddoksori.com" 선택 → Delete hosted zone
3. 확인란에 "delete" 입력 → "Delete" 클릭
```

#### 도메인 자동갱신 비활성화

```
1. Route 53 Console → Registered domains → ddoksori.com
2. Auto-renew: "Disable" 클릭
   - 현재 등록 기간 만료 시 도메인이 해제됨
   - 도메인은 만료일까지 소유 (이미 지불한 $13/년)
```

> **도메인 재사용 시**: Hosted Zone 재생성 ($0.50/월) → A 레코드 새 IP로 설정

### 7.8 IAM 정리

> IAM은 무료이지만, 사용하지 않는 Role/Policy는 보안상 삭제 권장.

#### DDOKSORI IAM 리소스 목록

| 리소스 | 이름 | 용도 |
|--------|------|------|
| Role | `ddoksori-github-actions-role` | GitHub Actions OIDC |
| Role | `ddoksori-ec2-role` | EC2 → ECR/Secrets 접근 |
| Policy | `AmazonEC2ContainerRegistryReadOnly` (AWS 관리) | ECR 읽기 |
| Policy | `SecretsManagerReadWrite` (AWS 관리) | Secrets Manager |
| Policy | 인라인 정책 (ECR push 등) | GitHub Actions용 |
| OIDC Provider | `token.actions.githubusercontent.com` | GitHub Actions 인증 |

#### 정리 순서 (의존성 주의)

```
1. IAM Console → Roles → "ddoksori-github-actions-role"
   - Permissions 탭 → 모든 Policy "Detach" (Remove)
   - Role 삭제: "Delete" → 역할 이름 입력 → "Delete"

2. IAM Console → Roles → "ddoksori-ec2-role"
   - Permissions 탭 → 모든 Policy "Detach"
   - Role 삭제

3. IAM Console → Identity providers
   - "token.actions.githubusercontent.com" 선택 → Delete
   - ⚠️ 다른 프로젝트도 이 OIDC를 사용 중이면 삭제하지 마세요
   - 확인 방법: IAM → Roles에서 이 OIDC를 Trust하는 다른 Role이 있는지 확인

4. 커스텀 정책 삭제 (있는 경우):
   - IAM → Policies → 필터: "Customer managed"
   - ddoksori 관련 정책 선택 → Actions → Delete
```

### 7.9 보안 그룹 및 키 페어 정리

> 무료이지만, 미사용 리소스 정리는 보안 관리에 도움됩니다.

#### 보안 그룹 삭제

```
1. EC2 Console → Network & Security → Security Groups
2. ddoksori 관련 보안 그룹 선택:
   - ddoksori-ec2-sg (SSH + HTTP + HTTPS)
   - ddoksori-rds-sg (PostgreSQL 5432)
   - ⚠️ "default" 보안 그룹은 삭제 불가 (VPC 기본)
3. Actions → Delete security groups
4. "Delete" 확인
```

> **Note**: EC2, RDS가 먼저 삭제되어야 보안 그룹 삭제 가능. 사용 중인 보안 그룹은 삭제 거부됨.

#### 키 페어 삭제

```
1. EC2 Console → Network & Security → Key Pairs
2. ddoksori용 키 페어 선택
3. Actions → Delete → "Delete" 확인
4. 로컬 PC의 .pem 파일도 안전하게 삭제
```

### 7.10 GitHub Secrets 정리 (선택)

> AWS 리소스는 아니지만, 더 이상 유효하지 않은 시크릿을 정리합니다.

```
1. GitHub → Repository → Settings → Secrets and variables → Actions
2. 삭제 대상 시크릿:
   - AWS_ROLE_ARN (IAM Role 삭제 후 무효)
   - EC2_SSH_KEY (EC2 삭제 후 무효)
   - DB_HOST, DB_USER, DB_NAME, DB_PASSWORD (RDS 삭제 후 무효)
   - DISCORD_WEBHOOK (선택: 웹훅 자체는 Discord에서 관리)
3. 각 시크릿 옆 "Delete" 클릭
```

> **유지 권장**: `OPENAI_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `GOOGLE_GENERATIVE_AI_API_KEY` 등
> 외부 API 키는 다른 프로젝트에서 재사용 가능하므로 유지.

### 7.11 정리 완료 확인 체크리스트

| 순서 | 항목 | 확인 |
|------|------|------|
| 1 | EC2 인스턴스 Terminated | ⬜ |
| 2 | 탄력적 IP Released | ⬜ |
| 3 | RDS 인스턴스 Deleted (최종 스냅샷 생성) | ⬜ |
| 4 | Secrets Manager 12개 시크릿 Deleted | ⬜ |
| 5 | S3 버킷 Emptied + Deleted | ⬜ |
| 6 | ECR 리포지토리 2개 Deleted | ⬜ |
| 7 | Route 53 Hosted Zone 삭제 | ⬜ |
| 8 | Route 53 도메인 자동갱신 Disabled | ⬜ |
| 9 | IAM Role/Policy/OIDC 삭제 | ⬜ |
| 10 | 보안 그룹 삭제 | ⬜ |
| 11 | 키 페어 삭제 | ⬜ |
| 12 | GitHub Secrets 정리 | ⬜ |
| 13 | AWS Billing → 24시간 후 과금 $0 확인 | ⬜ |

> **최종 확인**: AWS Console → Billing and Cost Management → Bills에서
> 24시간 후 과금 항목이 없는지 확인합니다. Route 53 도메인 등록비는
> 이미 선불이므로 만료일까지 유지됩니다.

---

## 참고 문서

- 아카이브된 배포 가이드: `docs/_archive/plans/deploy/`
- 현재 Docker 설정 (개발): `docker-compose.yml`
- 테스트 설정: `backend/pytest.ini`
- 환경변수 템플릿: `.env.example`
- AWS Secrets Manager 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`
- MAS v2 아키텍처 설계: `docs/plans/2026-01-28-mas-architecture-v2-design.md`
- 도메인/HTTPS 상세 가이드: `.omc/plans/domain-https-setup.md`

---

## Appendix: 변경 이력

### 2026-01-28: Backend 리팩토링 반영

CI/CD에 영향 있는 변경:
- 테스트 서비스: PostgreSQL만 → PostgreSQL + Redis (3계층 캐싱 테스트)
- 테스트 마커: `unit or integration` → `not skip_ci and not llm` (16개 마커 체계)
- uv 설치: `pip install uv` → `COPY --from=ghcr.io` (Dockerfile과 동일)
- 환경변수: Redis 설정 추가

CI/CD 영향 없는 추가 모듈: `app/common/cache/`, `app/llm/providers/`, `app/common/embedding/`, `app/common/config.py`, `app/agents/followup/`, `app/agents/retrieval/trace.py`, `app/agents/retrieval/tools/unified_retriever.py`, `app/database/migrations/004_add_rrf_search_functions.sql`, `app/auth/`, `scripts/testing/e2e/`

### 2026-01-29: MAS v2 아키텍처 반영

CI/CD 영향 없음. 주요 변경:
- Retrieval Agent: 4개 → 3개 (counsel → case 통합)
- Supervisor 모델: gpt-4o → gpt-4o-mini
- 추가: Agent Registry, 재생성 루프, ChatState 분할

상세 설계: `docs/plans/2026-01-28-mas-architecture-v2-design.md`

### 2026-01-29: AWS Secrets Manager 통합

Step 3에 통합됨. 상세 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`

### 2026-02-01: AWS 인프라 초기 설정 가이드

Step 0으로 통합됨.

### 2026-02-03: 도메인 + HTTPS + ALB 검토

Step 6으로 추가됨.
- ALB 검토: 현재 단계에서 불필요 (비용 $24-38/월, EC2 1대)
- 도메인: Route 53 구매 → A 레코드 → 탄력적 IP 연결
- HTTPS: Let's Encrypt + Certbot Docker 컨테이너
- CI/CD 변경: EC2_HOST IP→도메인, 헬스체크 http→https
- 상세 가이드: `.omc/plans/domain-https-setup.md`

### 2026-02-03: AWS 리소스 정리 가이드

Step 7으로 추가됨.
- 도메인 등록을 제외한 전체 AWS 리소스 해제 절차
- EC2, RDS, Secrets Manager, S3, ECR, Route 53, IAM 정리
- 의존성 순서 고려한 10단계 정리 절차
- 정리 완료 시 월 ~$38-40 절감
