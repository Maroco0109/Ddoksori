# DDOKSORI CI/CD 설정 가이드

> **관련 문서**: [CI/CD Pipeline Design](../plans/2026-01-28-cicd-pipeline-design.md) (아키텍처 및 설계 의사결정)

이 문서는 GitHub Actions 기반 CI/CD 파이프라인을 처음부터 설정하는 단계별 가이드입니다.

---

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [Phase A: 인프라 준비 (main merge 전 완료 필수)](#2-phase-a-인프라-준비-main-merge-전-완료-필수)
3. [Phase B: CI 검증 (PR 단계)](#3-phase-b-ci-검증-pr-단계)
4. [Phase C: main merge → 자동 배포](#4-phase-c-main-merge--자동-배포)
5. [워크플로우 참조](#5-워크플로우-참조)
6. [GitHub Secrets 설정](#6-github-secrets-설정)
7. [도메인 + HTTPS 적용](#7-도메인--https-적용)
8. [운영 가이드](#8-운영-가이드)
9. [트러블슈팅](#9-트러블슈팅)
10. [전체 진행 상태 추적](#10-전체-진행-상태-추적)

---

## ⚠️ 중요: 실행 순서

**main에 merge하면 자동으로 EC2 배포가 실행됩니다.** 따라서 반드시 아래 순서를 지켜야 합니다:

```
1. Phase A 완료 (모든 인프라 + Secrets)  ← EC2까지 포함!
2. Phase B: PR로 CI 검증
3. Phase C: main merge → 자동 배포 성공
```

Phase A를 완료하지 않고 main에 merge하면 `deploy-staging.yml`이 실행되어 **SSH 연결 실패**합니다.

---

## 1. 사전 요구사항

- AWS 계정 (IAM 관리자 권한)
- GitHub 리포지토리 관리 권한 (Settings 접근)
- AWS CLI v2 설치

---

## 2. Phase A: 인프라 준비 (main merge 전 완료 필수)

> **이 Phase의 모든 단계를 완료해야 main merge가 가능합니다.**
> main merge 시 `deploy-staging.yml`이 자동 실행되므로, EC2와 모든 Secrets가 준비되어 있어야 합니다.

### 개념 설명: 왜 이런 설정이 필요한가?

GitHub Actions가 AWS 서비스(ECR, EC2 등)를 사용하려면 **인증**이 필요합니다.

```
GitHub Actions 워크플로우
    │
    │  "나 ECR에 이미지 올리고 싶어"
    ▼
AWS: "너 누구야? 권한 있어?"
    │
    │  인증 방법 2가지:
    │  ├─ (구식) Access Key/Secret Key 직접 저장 → 유출 위험!
    │  └─ (신식) OIDC → GitHub이 신원 증명 → AWS가 임시 토큰 발급 ✅
    ▼
AWS: "GitHub Actions가 보증하네. 15분짜리 임시 권한 줄게"
```

**핵심 개념 정리:**

| 용어 | 쉬운 설명 | 비유 |
|------|----------|------|
| **IAM** | AWS의 사용자/권한 관리 시스템 | 회사 출입 관리 시스템 |
| **IAM Role** | "이런 권한을 가진 역할" 정의 | 출입증 (누구든 이 출입증 가지면 특정 구역 출입 가능) |
| **IAM Policy** | 구체적인 권한 목록 | 출입증에 적힌 "A동 출입 가능, B동 불가" 같은 권한 |
| **OIDC** | 외부 서비스가 신원 증명하는 표준 방식 | "저 사람 우리 회사 직원 맞아요" 라고 보증해주는 것 |
| **ARN** | AWS 리소스의 고유 주소 | 주민등록번호 같은 고유 식별자 |
| **ECR** | AWS의 Docker 이미지 저장소 | Docker Hub의 AWS 버전 |

---

### A-1. AWS CLI v2 설치

로컬에서 AWS 명령어를 실행하기 위한 도구입니다.

```bash
# Linux (x86_64)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 확인
aws --version
# 출력 예: aws-cli/2.x.x Python/3.x.x Linux/...
```

#### AWS CLI 초기 설정

```bash
aws configure
```

입력 프롬프트가 나오면:
```
AWS Access Key ID [None]: AKIA1234567890EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: ap-northeast-2
Default output format [None]: json
```

> **Access Key 발급 방법:**
> 1. AWS Console → IAM → Users → 본인 계정 클릭
> 2. Security credentials 탭 → Create access key
> 3. Use case: "Command Line Interface (CLI)" 선택
> 4. Key 생성 후 **Secret Access Key는 이때만 볼 수 있음** (꼭 저장!)

---

### A-2. OIDC Identity Provider 생성

**목적:** AWS에게 "GitHub Actions를 신뢰해도 돼"라고 알려주는 설정

```
GitHub Actions 실행 시:
  GitHub: "이 워크플로우는 maroco/LLM 리포의 main 브랜치에서 왔어"
           (JWT 토큰으로 서명해서 증명)
     │
     ▼
  AWS OIDC Provider: "GitHub이 보증하네, 진짜인지 검증해볼게"
     │
     ▼ (토큰 검증 성공)
  AWS: "OK, 이 Role의 권한을 15분간 줄게"
```

#### 설정 방법 (AWS Console)

1. **AWS Console 접속** → 검색창에 `IAM` 입력 → IAM 클릭

2. **왼쪽 메뉴에서 "Identity providers" 클릭**

3. **"Add provider" 버튼 클릭**

4. **아래 값 입력:**

   | 필드 | 입력값 | 설명 |
   |------|--------|------|
   | Provider type | `OpenID Connect` | OIDC 방식 선택 |
   | Provider URL | `https://token.actions.githubusercontent.com` | GitHub Actions의 토큰 발급 주소 |
   | Audience | `sts.amazonaws.com` | AWS STS(토큰 서비스)가 수신자임을 명시 |

5. **"Get thumbprint" 버튼 클릭** (자동으로 지문 생성됨)

6. **"Add provider" 클릭하여 완료**

> **확인:** Identity providers 목록에 `token.actions.githubusercontent.com`이 보이면 성공

---

### A-3. IAM Role 생성 (OIDC 연동)

**목적:** "GitHub Actions가 AWS에서 무엇을 할 수 있는지" 권한 정의

```
IAM Role = 권한 묶음
  ├─ Trust Policy: "누가 이 역할을 맡을 수 있나?" → GitHub Actions
  └─ Permission Policy: "이 역할로 뭘 할 수 있나?" → ECR에 이미지 푸시
```

#### 설정 방법 (AWS Console)

1. **IAM → 왼쪽 메뉴 "Roles" → "Create role" 버튼**

2. **Step 1: Select trusted entity**
   - **Trusted entity type:** `Web identity` 선택
   - **Identity provider:** 드롭다운에서 `token.actions.githubusercontent.com` 선택
   - **Audience:** `sts.amazonaws.com` 선택
   - **GitHub organization:** GitHub 사용자명 또는 조직명 입력 (예: `maroco`)
     > 개인 리포면 본인 GitHub 사용자명, 조직 리포면 조직명 입력
   - **GitHub repository (선택):** 특정 리포만 허용하려면 입력 (예: `LLM`)
     > 비워두면 해당 org/user의 모든 리포에서 사용 가능
   - **GitHub branch (선택):** 특정 브랜치만 허용하려면 입력 (예: `main`)
   - **Next** 클릭

3. **Step 2: Add permissions**
   - 검색창에 `AmazonEC2ContainerRegistryPowerUser` 입력
   - 체크박스 선택 (ECR에 이미지 push/pull 권한)
   - **Next** 클릭

4. **Step 3: Name, review, and create**
   - **Role name:** `ddoksori-github-actions` (원하는 이름)
   - **Create role** 클릭

#### Trust Policy 확인

Step 1에서 GitHub organization/repository를 입력했다면 Trust Policy가 **자동 생성**됩니다.

**확인 방법:**
1. 생성된 Role 클릭 → **"Trust relationships"** 탭
2. Trust policy JSON 확인

**자동 생성된 예시 (maroco/LLM 리포 전체 허용):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:maroco/LLM:*"
        }
      }
    }
  ]
}
```

**Condition 설명:**
- `aud`: Audience - `sts.amazonaws.com`이어야 함
- `sub`: Subject - 어떤 리포/브랜치에서 요청이 왔는지
  - `repo:maroco/LLM:*` → maroco/LLM 리포의 모든 브랜치/태그 허용
  - `repo:maroco/LLM:ref:refs/heads/main` → main 브랜치만 허용

#### (선택) Trust Policy 수동 수정

Console에서 설정을 빠뜨렸거나 나중에 수정하려면:

1. **IAM → Roles → 생성한 Role → "Trust relationships" 탭**
2. **"Edit trust policy"** 클릭
3. `Condition` 부분의 `sub` 값 수정
4. **"Update policy"** 클릭

#### Role ARN 복사 (나중에 필요)

Role 상세 페이지 상단에 **ARN**이 표시됩니다:
```
arn:aws:iam::123456789012:role/ddoksori-github-actions
```
이 값을 복사해두세요 (A-5에서 사용).

---

### A-4. ECR 리포지토리 생성

**목적:** Docker 이미지를 저장할 공간 만들기

```
ECR (Elastic Container Registry)
  ├─ ddoksori-backend   ← Backend Docker 이미지 저장
  └─ ddoksori-frontend  ← Frontend Docker 이미지 저장
```

#### 방법 1: AWS Console

1. AWS Console → 검색창에 `ECR` → Elastic Container Registry 클릭
2. **"Create repository"** 클릭
3. Repository name: `ddoksori-backend` 입력 → Create
4. 같은 방법으로 `ddoksori-frontend` 생성

#### 방법 2: AWS CLI (더 빠름)

```bash
# Backend 리포지토리 생성
aws ecr create-repository \
  --repository-name ddoksori-backend \
  --region ap-northeast-2

# Frontend 리포지토리 생성
aws ecr create-repository \
  --repository-name ddoksori-frontend \
  --region ap-northeast-2
```

**출력 예시:**
```json
{
    "repository": {
        "repositoryArn": "arn:aws:ecr:ap-northeast-2:123456789012:repository/ddoksori-backend",
        "repositoryUri": "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/ddoksori-backend",
        ...
    }
}
```

> **repositoryUri**는 나중에 Docker 이미지 태그에 사용됩니다.

---

### A-5. GitHub Secrets 등록

**목적:** GitHub Actions가 AWS Role을 사용하도록 ARN 저장

GitHub Actions 워크플로우에서 이렇게 사용됩니다:
```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}  # ← 여기서 사용
    aws-region: ap-northeast-2
```

#### 설정 방법

1. **GitHub 리포지토리 페이지 → Settings 탭**

2. **왼쪽 메뉴: Security → Secrets and variables → Actions**

3. **"New repository secret" 버튼 클릭**

4. **입력:**
   - **Name:** `AWS_ROLE_ARN`
   - **Secret:** `arn:aws:iam::123456789012:role/ddoksori-github-actions` (A-3에서 복사한 값)

5. **"Add secret" 클릭**

---

### A-6. 워크플로우 파일 확인

`.github/workflows/` 디렉토리에 다음 파일들이 있어야 합니다:

| 파일 | 용도 | 트리거 |
|------|------|--------|
| `lint.yml` | 코드 스타일 검사 | PR, push to main |
| `test.yml` | 테스트 실행 | PR, push to main |
| `build.yml` | Docker 이미지 빌드 & ECR 푸시 | push to main, 태그 생성 |

```bash
# 확인
ls -la .github/workflows/
```

---

### A-7. CI + 빌드 검증

#### 테스트 1: Lint & Test 확인

1. 아무 파일이나 수정 후 PR 생성
2. GitHub → PR 페이지 → 하단 "Checks" 섹션 확인
3. `Lint`와 `Test` 잡이 녹색 체크되면 성공

#### 테스트 2: Build & ECR Push 확인

1. PR을 main에 머지
2. GitHub → Actions 탭 → "Build and Push" 워크플로우 클릭
3. 성공하면 ECR에 이미지가 올라감

**ECR에서 이미지 확인:**
```bash
aws ecr describe-images \
  --repository-name ddoksori-backend \
  --region ap-northeast-2
```

또는 AWS Console → ECR → ddoksori-backend → Images 탭

---

---

### A-8. EC2 인스턴스 생성

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
| 22 | TCP | My IP | SSH - 개발자 접속용 |
| 80 | TCP | 0.0.0.0/0 | HTTP (Nginx → Backend 프록시) |

---

### A-9. GitHub Actions SSH 동적 IP 화이트리스트 설정

GitHub Actions Runner는 매번 다른 IP에서 실행됩니다. **배포 시에만** Runner IP를 보안 그룹에 열고, **끝나면 즉시 닫는** 방식이 업계 표준입니다.

#### 작동 원리

```
배포 워크플로우 시작
  │
  ├─ 1) Runner의 퍼블릭 IP 확인 (예: 20.1.2.3)
  ├─ 2) 보안 그룹에 SSH 규칙 추가: 20.1.2.3/32 → 포트 22
  ├─ 3) SSH로 EC2 접속 → docker compose pull → up -d
  ├─ 4) 헬스체크
  └─ 5) 보안 그룹에서 SSH 규칙 제거: 20.1.2.3/32 (if: always → 실패해도 반드시 실행)
```

#### 1단계: CI/CD 전용 보안 그룹 생성

```
EC2 → Security Groups → Create security group

  이름: ddoksori-github-actions-ssh
  설명: Temporary SSH access for GitHub Actions deployment
  VPC: EC2와 동일한 VPC 선택
  인바운드 규칙: 비워둠 (워크플로우가 동적으로 관리)
```

생성 후 **보안 그룹 ID** (예: `sg-0abc1234def56789`)를 메모합니다.

이 보안 그룹을 EC2 인스턴스에 **추가** 연결합니다:

```
EC2 → 인스턴스 선택 → Actions → Security → Change security groups
  → "ddoksori-github-actions-ssh" 추가 → Save
```

#### 2단계: IAM 정책 생성 & Role에 연결

**IAM → Policies → Create policy → JSON:**

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

정책 이름: `ddoksori-github-actions-sg-policy`

기존 OIDC Role (`ddoksori-github-actions`)에 이 정책을 **연결(Attach)**:

```
IAM → Roles → ddoksori-github-actions → Permissions → Add permissions
  → Attach policies → "ddoksori-github-actions-sg-policy" 선택 → Add
```

#### 3단계: GitHub Secret 추가

```
GitHub repo → Settings → Secrets and variables → Actions → New repository secret

  Name:  AWS_SECURITY_GROUP_ID
  Value: sg-0abc1234def56789    (1단계에서 메모한 보안 그룹 ID)
```

---

### A-10. 탄력적 IP (Elastic IP) 할당

EC2 퍼블릭 IP는 재부팅 시 변경되므로, 고정 IP를 할당해야 배포 워크플로우가 안정적으로 동작합니다.

1. **EC2 → Elastic IPs → Allocate Elastic IP address** 클릭
2. 할당된 IP 선택 → **Actions → Associate Elastic IP address**
3. 대상 EC2 인스턴스(`ddoksori-staging`) 선택 → Associate

> **비용:** EC2에 연결된 상태면 **무료**. 연결하지 않고 방치하면 과금 발생.

---

### A-11. EC2 초기 설정 (터미널)

SSH로 접속 후 아래 명령어 실행:

```bash
# 1) SSH 접속
ssh -i "다운받은키.pem" ubuntu@<탄력적IP>

# 2) Docker + 기본 패키지 설치
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 curl unzip
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ubuntu

# 3) AWS CLI v2 설치
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# 4) 재접속 (docker 그룹 반영)
exit
ssh -i "다운받은키.pem" ubuntu@<탄력적IP>

# 5) 설치 확인
docker --version
docker compose version
aws --version

# 6) 프로젝트 디렉토리 생성
mkdir -p /home/ubuntu/ddoksori/backups
```

---

### A-12. EC2에 IAM Role 연결

EC2가 ECR에서 이미지를 pull하려면 별도 IAM Role이 필요:

1. **IAM → Roles → Create role**
   - Trusted entity: **AWS service → EC2**
   - 정책: `AmazonEC2ContainerRegistryReadOnly`
   - Role 이름: `ddoksori-ec2-role`

2. **EC2 Console → 인스턴스 선택 → Actions → Security → Modify IAM role**
   - 위에서 생성한 `ddoksori-ec2-role` 선택

> **Note:** AWS Secrets Manager도 사용할 경우 `SecretsManagerReadWrite` 정책도 추가.

---

### A-13. 프로젝트 코드 배치 (git clone)

```bash
# EC2에서 실행
cd /home/ubuntu/ddoksori
git clone <repo-url> .    # ← 마지막 "." 필수!
```

> **주의:** `.` 없이 `git clone <url>`을 실행하면 `/home/ubuntu/ddoksori/LLM/` 하위에 코드가 생성되어 워크플로우 경로와 불일치합니다.

clone 후 확인:
```bash
ls /home/ubuntu/ddoksori/docker-compose.prod.yml   # 파일이 보여야 정상
```

---

### A-14. 추가 GitHub Secrets 등록

| Secret Name | 값 | 필수 |
|-------------|---|------|
| `EC2_SSH_KEY` | EC2 키 페어의 `.pem` 파일 내용 전체 | O |
| `OPENAI_API_KEY` | OpenAI API 키 (main 전체 테스트용) | O |
| `DISCORD_WEBHOOK` | Discord 웹훅 URL | 선택 |

> **EC2_SSH_KEY 등록 방법:** `.pem` 파일을 텍스트 편집기로 열어 `-----BEGIN RSA PRIVATE KEY-----`부터 `-----END RSA PRIVATE KEY-----`까지 전체 복사하여 등록.

---

### A-15. deploy-staging.yml 내 EC2_HOST 설정

`deploy-staging.yml`과 `deploy-production.yml`에서 EC2_HOST를 실제 탄력적 IP로 수정:

```yaml
env:
  EC2_HOST: <탄력적IP>  # 예: 15.165.215.141
```

---

### Phase A 완료 체크리스트

**AWS 기본 설정:**
- [ ] AWS CLI 설치 & `aws configure` 완료
- [ ] OIDC Identity Provider 생성 (`token.actions.githubusercontent.com`)
- [ ] IAM Role 생성 (`ddoksori-github-actions`)
- [ ] IAM Role Trust Policy에 리포 제한 추가 (`repo:YOUR_ORG/YOUR_REPO:*`)
- [ ] ECR 리포지토리 2개 생성 (`ddoksori-backend`, `ddoksori-frontend`)

**EC2 설정:**
- [ ] EC2 인스턴스 생성 (t3.small, Ubuntu 24.04 LTS)
- [ ] 보안 그룹 설정 (22, 80)
- [ ] 동적 IP 화이트리스트용 보안 그룹 생성 및 IAM 정책 연결
- [ ] 탄력적 IP 할당 및 EC2 연결
- [ ] Docker + Docker Compose 설치
- [ ] EC2 IAM Role 연결 (ECR ReadOnly)
- [ ] `/home/ubuntu/ddoksori/` 디렉토리 + `docker-compose.prod.yml` 배치

**GitHub Secrets:**
- [ ] `AWS_ROLE_ARN` 등록
- [ ] `AWS_SECURITY_GROUP_ID` 등록
- [ ] `EC2_SSH_KEY` 등록
- [ ] `OPENAI_API_KEY` 등록

**워크플로우 설정:**
- [ ] `deploy-staging.yml` 내 EC2_HOST 실제 값으로 설정

> **⚠️ 위 체크리스트를 모두 완료한 후에만 Phase B로 진행하세요!**

---

### 트러블슈팅: Phase A

#### "Error: Not authorized to perform sts:AssumeRoleWithWebIdentity"

**원인:** Trust Policy 설정 오류

**확인:**
1. IAM → Roles → 생성한 Role → Trust relationships 탭
2. `Condition` 부분에 리포 경로가 정확한지 확인
3. AWS 계정 ID가 맞는지 확인

#### "Error: Could not load credentials from any providers"

**원인:** GitHub Secrets에 `AWS_ROLE_ARN`이 없거나 값이 잘못됨

**확인:**
1. GitHub → Settings → Secrets → `AWS_ROLE_ARN` 존재 여부
2. 값이 `arn:aws:iam::...`으로 시작하는지

#### ECR push 시 "denied: Your authorization token has expired"

**원인:** ECR 로그인 토큰 만료 (12시간 유효)

**해결:** 워크플로우에서 `aws-actions/amazon-ecr-login@v2` 액션이 있는지 확인

---

## 3. Phase B: CI 검증 (PR 단계)

> **Phase A가 완료된 후에만 진행하세요.**
> 이 단계에서는 main에 merge하지 않고 PR로만 CI를 검증합니다.

### B-1. PR 생성 및 CI 확인

1. feature 브랜치 생성 후 아무 파일이나 수정
2. PR 생성 (main으로)
3. GitHub → PR 페이지 → 하단 "Checks" 섹션 확인
4. `Lint`와 `Test` 잡이 녹색 체크되면 성공

### B-2. 확인 항목

| 워크플로우 | 트리거 | 확인 사항 |
|------------|--------|-----------|
| `lint.yml` | PR 생성 | `ruff check`, `ruff format --check` 통과 |
| `test.yml` | PR 생성 | pytest 통과 (PostgreSQL + Redis 서비스 컨테이너) |

> **⚠️ 주의:** 이 단계에서는 **merge하지 마세요!** merge하면 build.yml → deploy-staging.yml이 자동 실행됩니다.

### Phase B 완료 체크리스트

- [ ] PR 생성 시 lint.yml 정상 동작 확인
- [ ] PR 생성 시 test.yml 정상 동작 확인
- [ ] Phase A 체크리스트 전체 완료 재확인

---

## 4. Phase C: main merge → 자동 배포

> **Phase A + B가 모두 완료된 후에만 진행하세요.**

### C-1. main merge

1. Phase B에서 생성한 PR을 main에 merge
2. 다음 워크플로우가 **자동으로 순차 실행**됩니다:

```
main merge
    │
    ▼
build.yml (Docker 빌드 + ECR push)
    │ 성공 시
    ▼
deploy-staging.yml (EC2 배포 + Health Check)
    │
    ▼
완료!
```

### C-2. 배포 확인

1. GitHub → Actions 탭에서 `Build and Push` 워크플로우 성공 확인
2. `Deploy to Staging` 워크플로우 자동 실행 확인
3. 배포 완료 후:
   - `http://<탄력적IP>/health` 접속하여 헬스체크 확인
   - `http://<탄력적IP>` 접속하여 Frontend 확인

### C-3. Production 배포 (선택)

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

### Phase C 완료 체크리스트

- [ ] main merge → build.yml 성공
- [ ] deploy-staging.yml 자동 실행 및 성공
- [ ] 헬스체크 (`/health`) 정상 응답
- [ ] Frontend 접속 확인
- [ ] (선택) GitHub Environments: production 환경 + 수동 승인 설정
- [ ] (선택) v* 태그 → production 배포 테스트 성공
- [ ] (선택) Discord 알림 수신 확인

---

## 5. 워크플로우 참조

### Lint (`.github/workflows/lint.yml`)

- **트리거**: PR 생성, Push to main
- **작업**: Backend (`black --check`, `isort --check`), Frontend (`npm run lint`)

### Test (`.github/workflows/test.yml`)

- **트리거**: PR 생성, Push to main
- **서비스**: PostgreSQL (pgvector:pg16) + Redis 7-alpine
- **테스트 전략**:
  - PR: `pytest -m "not skip_ci and not llm"` (빠른 피드백)
  - main: `pytest -m "not skip_ci"` (전체 테스트, LLM 포함)

### Build (`.github/workflows/build.yml`)

- **트리거**: Push to main, Tag 생성 (`v*`)
- **작업**: Docker Buildx 빌드 + ECR 푸시 (GHA 캐시 활용)

### Deploy Staging (`.github/workflows/deploy-staging.yml`)

- **트리거**: Build 워크플로우 성공 완료 시 (main 브랜치)
- **특징**: 5회 재시도 헬스체크, Discord 알림

### Deploy Production (`.github/workflows/deploy-production.yml`)

- **트리거**: `v*` 태그 생성
- **특징**: GitHub 수동 승인, 배포 전 백업, 10회 재시도 헬스체크, 자동 롤백 잡

### DB Backup (`.github/workflows/db-backup.yml`)

- **트리거**: 매주 일요일 04:00 UTC (한국시간 13:00) + 수동 트리거
- **작업**: `pg_dump` → S3 업로드, 실패 시 GitHub Issue 자동 생성

---

## 6. GitHub Secrets 설정

### CI/CD 파이프라인용

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `AWS_ROLE_ARN` | build, deploy-*, db-backup | AWS OIDC Role ARN |
| `EC2_SSH_KEY` | deploy-staging, deploy-production | EC2 SSH 개인키 |
| `OPENAI_API_KEY` | test | LLM 테스트용 API 키 |
| `DISCORD_WEBHOOK` | deploy-* | Discord 알림 웹훅 URL |
| `AWS_SECURITY_GROUP_ID` | deploy-* | 동적 IP 화이트리스트용 보안 그룹 ID |

### DB 백업용

| Secret Name | Description |
|-------------|-------------|
| `DB_HOST` | RDS 호스트 주소 |
| `DB_USER` | RDS 사용자명 |
| `DB_NAME` | RDS 데이터베이스명 |
| `DB_PASSWORD` | RDS 비밀번호 |

### AWS Secrets Manager (EC2 런타임용)

| Secret Path | 주입되는 환경변수 |
|-------------|-------------------|
| `ddoksori/{env}/database` | DB_HOST, DB_USER, DB_PASSWORD, DATABASE_URL |
| `ddoksori/{env}/llm` | OPENAI_API_KEY, ANTHROPIC_API_KEY |
| `ddoksori/{env}/oauth/google` | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET |
| `ddoksori/{env}/oauth/naver` | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET |
| `ddoksori/{env}/security` | JWT_SECRET_KEY, SECRET_KEY |
| `ddoksori/{env}/infra` | HF_TOKEN, EXAONE_RUNPOD_API_KEY |

---

## 7. 도메인 + HTTPS 적용

### 7.1 도메인 구매 (Route 53)

```
1. AWS Console → Route 53 → Registered domains → Register Domain
2. 도메인 검색 (예: ddoksori.com) → 선택 → 결제 (~$13/년)
3. 이메일 인증 링크 클릭
4. Hosted Zone → Create Record:
   - A 레코드: (비워둠) → <탄력적 IP>
   - CNAME: www → ddoksori.com
5. DNS 전파 확인: nslookup ddoksori.com
```

### 7.2 EC2 보안 그룹 변경

443 포트 추가:

```
EC2 Console → 인스턴스 → Security 탭 → 보안 그룹 클릭
  → Edit inbound rules → Add rule:
    Type: HTTPS, Port: 443, Source: 0.0.0.0/0
```

### 7.3 HTTPS 적용 (Let's Encrypt + Certbot)

`docker-compose.prod.yml`에 certbot 서비스 및 볼륨 추가, `nginx.conf`에 SSL 설정 추가가 필요합니다. 상세 설정은 [CI/CD Pipeline Design](../plans/2026-01-28-cicd-pipeline-design.md)의 Step 6을 참조하세요.

---

## 8. 운영 가이드

| 작업 | 트리거 | 자동화 |
|------|--------|--------|
| 코드 린트 | PR 생성/Push to main | 자동 |
| 테스트 실행 | PR 생성/Push to main | 자동 |
| Docker 이미지 빌드 | Push to main / Tag 생성 | 자동 |
| Staging 배포 | main 머지 후 Build 성공 | 자동 |
| Production 배포 | v* 태그 생성 | 자동 (수동 승인) |
| DB 백업 | 매주 일요일 13:00 KST | 자동 |
| Production 롤백 | 배포 실패 시 | 자동 (수동 트리거 가능) |

### 수동 롤백 절차

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

## 9. 트러블슈팅

### Runner IP 화이트리스트 관련

**문제**: SSH 연결 실패 (Connection timed out)

**확인**:
1. GitHub Actions 로그에서 "Opened SSH for X.X.X.X/32" 메시지 확인
2. AWS 콘솔에서 보안 그룹 인바운드 규칙 확인
3. IAM 정책의 보안 그룹 ARN 확인

**문제**: 보안 그룹 규칙이 삭제되지 않음

**원인**: 워크플로우가 중단되거나 `if: always()` 누락

**해결**: AWS 콘솔에서 수동 삭제
```
EC2 → Security Groups → ddoksori-github-actions-ssh → Edit inbound rules
  → 남아있는 22번 포트 규칙 삭제
```

### ECR 관련

**문제**: `docker login` 실패

**확인**: IAM Role에 `AmazonEC2ContainerRegistryPowerUser` 정책 연결 확인

### 기타

상세 트러블슈팅은 [deployment-troubleshooting.md](./deployment-troubleshooting.md) 참조.

---

## 10. 전체 진행 상태 추적

### Phase A: 인프라 준비 (main merge 전 필수 완료)

| 단계 | 항목 | 상태 |
|------|------|------|
| **A-1** | AWS CLI v2 설치 | |
| **A-2** | OIDC Identity Provider 생성 | |
| **A-3** | IAM Role 생성 | |
| **A-4** | ECR 리포지토리 생성 | |
| **A-5** | GitHub Secrets: AWS_ROLE_ARN | |
| **A-6** | 워크플로우 파일 확인 | |
| **A-7** | (PR로만) CI 검증 | |
| **A-8** | EC2 인스턴스 생성 | |
| **A-9** | 동적 IP 화이트리스트 설정 | |
| **A-10** | 탄력적 IP 할당 | |
| **A-11** | EC2 초기 설정 | |
| **A-12** | EC2 IAM Role 연결 | |
| **A-13** | docker-compose.prod.yml 배치 | |
| **A-14** | 추가 GitHub Secrets 등록 | |
| **A-15** | EC2_HOST 설정 | |

### Phase B: CI 검증 (PR 단계)

| 단계 | 항목 | 상태 |
|------|------|------|
| **B-1** | PR 생성 및 lint.yml 확인 | |
| **B-2** | PR 생성 및 test.yml 확인 | |

### Phase C: main merge → 자동 배포

| 단계 | 항목 | 상태 |
|------|------|------|
| **C-1** | main merge → build.yml 성공 | |
| **C-2** | deploy-staging.yml 자동 배포 성공 | |
| **C-3** | Health Check 통과 | |
| **C-4** | (선택) Production 배포 테스트 | |

---

## 비용 참고 (AWS)

- EC2 t3.small: ~$15/월
- RDS db.t3.micro: ~$15/월
- ECR: ~$1/월 (스토리지)
- S3 (DB 백업): ~$1/월
- Secrets Manager: ~$6/월 (7개 시크릿 x 2환경)
- **예상 총 비용**: $30-70/월

---

**문서 작성일**: 2026-02-03
**버전**: 1.0
