# AWS Secrets Manager 통합 설계

## 배경

현재 DDOKSORI 프로젝트는 `.env` 파일로 19개 시크릿 + 37개 설정을 관리 중.
CI/CD 파이프라인(GitHub Actions + AWS EC2/ECR) 설계에 맞춰 프로덕션 시크릿 관리를 AWS Secrets Manager로 전환.

## 결정 사항

- **방식**: AWS Secrets Manager (자동 로테이션 + 감사 로그)
- **비용**: 7개 시크릿 x $0.40 x 2환경(staging+prod) = ~$5.6/월
- **로컬 개발**: `.env` 유지 (변경 없음)
- **CI/CD**: GitHub Actions Secrets 유지 (변경 없음)
- **프로덕션**: Secrets Manager에서 앱 시작 시 로딩

## 시크릿 구조

네이밍: `ddoksori/{environment}/{category}`

| 시크릿 이름 | 내용 |
|------------|------|
| `ddoksori/{env}/database` | host, user, password, url |
| `ddoksori/{env}/llm` | openai_api_key, anthropic_api_key |
| `ddoksori/{env}/oauth/google` | client_id, client_secret |
| `ddoksori/{env}/oauth/kakao` | client_id, client_secret |
| `ddoksori/{env}/oauth/naver` | client_id, client_secret |
| `ddoksori/{env}/security` | jwt_secret_key, secret_key |
| `ddoksori/{env}/infra` | hf_token, exaone_runpod_api_key |

## 아키텍처

### 시크릿 로딩 우선순위

```
1. 환경변수 (최우선 - Docker/CI에서 주입)
2. AWS Secrets Manager (USE_AWS_SECRETS=true일 때)
3. .env 파일 (로컬 개발)
4. 기본값 (비-시크릿만)
```

### 환경별 전략

| 환경 | USE_AWS_SECRETS | 시크릿 소스 |
|------|----------------|-------------|
| 로컬 개발 | false (기본) | .env 파일 |
| CI/CD | false | GitHub Actions Secrets -> 환경변수 |
| Staging | true | AWS Secrets Manager (ddoksori/staging/*) |
| Production | true | AWS Secrets Manager (ddoksori/production/*) |

### 앱 코드 통합 방식

Pydantic 커스텀 소스 대신 **환경변수 사전 주입** 방식 사용:

```python
# secrets.py의 inject_aws_secrets()가 os.environ에 시크릿 주입
# -> AppConfig() 생성 시 기존 Pydantic Settings가 환경변수에서 자동 로딩
# -> 기존 하위 설정(DatabaseConfig, LLMConfig 등) 코드 변경 없음
```

이유:
- AppConfig는 default_factory로 하위 설정을 생성하고, 각 하위 설정이 독립적으로 env vars를 읽음
- 커스텀 소스를 모든 하위 설정에 적용하려면 코드 변경이 크지만, 환경변수 주입은 기존 코드 변경 없음
- 환경변수 우선순위: 기존 env var > AWS 시크릿 (os.environ에 없는 키만 주입)

## AWS 사전 설정 (콘솔/CLI)

### 시크릿 생성

```bash
# 7개 시크릿 생성 (staging 예시)
aws secretsmanager create-secret \
  --name ddoksori/staging/database \
  --secret-string '{"DB_HOST":"rds-endpoint","DB_USER":"postgres","DB_PASSWORD":"...","DATABASE_URL":"postgresql://..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/llm \
  --secret-string '{"OPENAI_API_KEY":"sk-...","ANTHROPIC_API_KEY":"sk-ant-..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/oauth/google \
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/oauth/kakao \
  --secret-string '{"KAKAO_CLIENT_ID":"...","KAKAO_CLIENT_SECRET":"..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/oauth/naver \
  --secret-string '{"NAVER_CLIENT_ID":"...","NAVER_CLIENT_SECRET":"..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/security \
  --secret-string '{"JWT_SECRET_KEY":"...","SECRET_KEY":"..."}'

aws secretsmanager create-secret \
  --name ddoksori/staging/infra \
  --secret-string '{"HF_TOKEN":"...","EXAONE_RUNPOD_API_KEY":"..."}'

# production도 동일 패턴으로 생성
```

### IAM 정책

EC2 Instance Profile에 다음 정책 부여:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:ap-northeast-2:*:secret:ddoksori/*"
    }
  ]
}
```

## 수정 파일 목록

| 파일 | 작업 | 설명 |
|------|------|------|
| `backend/app/common/secrets.py` | 신규 | AWS Secrets Manager SDK 래퍼 |
| `backend/app/common/config.py` | 수정 | `get_config()` 호출 전 시크릿 주입 |
| `backend/requirements.txt` | 수정 | `boto3` 추가 |
| `docker-compose.prod.yml` | 수정 | 시크릿 환경변수 -> AWS 설정으로 전환 |
| `docs/plans/2026-01-28-cicd-pipeline-design.md` | 수정 | Secrets Manager 반영 |

## 비용 요약

| 항목 | 비용 |
|------|------|
| Secrets Manager (7 시크릿 x 2 환경) | ~$5.6/월 |
| API 호출 (앱 시작 시 7회) | 거의 무시 가능 |
| **합계** | **~$6/월** |
