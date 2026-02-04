# SSL/HTTPS 배포 문제 해결 가이드

> **문제 발생일**: 2026-02-04
> **해결 완료일**: 2026-02-04
> **관련 이슈**: [#83](https://github.com/SKN19-FINAL-5team/LLM/issues/83)

## 목차

1. [문제 개요](#문제-개요)
2. [증상](#증상)
3. [시행착오 과정](#시행착오-과정)
4. [근본 원인](#근본-원인)
5. [해결 방법](#해결-방법)
6. [예방 조치](#예방-조치)
7. [관련 파일](#관련-파일)

---

## 문제 개요

HTTPS/SSL 지원을 추가한 후 GitHub Actions의 "Deploy to Staging" 워크플로우가 지속적으로 실패했습니다.

### 타임라인

| 시간 | 이벤트 |
|------|--------|
| T+0 | HTTPS/SSL 지원 기능 추가 (Let's Encrypt) |
| T+1 | Deploy to Staging 워크플로우 실패 시작 |
| T+2 | Health check 301 redirect 문제 발견 및 수정 |
| T+3 | SSL 인증서 마운트 문제로 계속 실패 |
| T+4 | 근본 원인 발견: 서버의 docker-compose.prod.yml 미동기화 |
| T+5 | CI/CD에 설정 파일 동기화 추가하여 해결 |

---

## 증상

### 1차 증상: External Health Check 실패

```
ERROR: External health check failed after 5 attempts
```

GitHub Actions 로그에서 `http://<EC2_PUBLIC_IP>/health` 요청이 301 redirect를 반환했습니다.

### 2차 증상: nginx 시작 실패

```
nginx: [emerg] cannot load certificate "/etc/letsencrypt/live/ddoksori.duckdns.org/fullchain.pem":
BIO_new_file() failed (SSL: error:80000002:system library::No such file or directory)
```

SSL 인증서 파일을 찾을 수 없다는 오류가 발생했습니다.

---

## 시행착오 과정

### 시도 1: HTTP Health Check Endpoint 추가 (부분 해결)

**가설**: HTTPS로 redirect 되어서 health check가 실패하는 것이다.

**조치**: `nginx.conf`의 HTTP 서버 블록에 `/health` 엔드포인트 추가

```nginx
# HTTP server block
server {
    listen 80;

    # Health check (no redirect for CI/CD and monitoring)
    location /health {
        proxy_pass http://backend:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Redirect to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
```

**결과**: ❌ 여전히 실패 - SSL 인증서 로드 자체가 안 됨

---

### 시도 2: 인증서 디렉토리 권한 수정

**가설**: `/etc/letsencrypt` 디렉토리 권한이 restrictive해서 Docker가 접근을 못하는 것이다.

**조치**:
```bash
sudo chmod -R 755 /etc/letsencrypt
```

**결과**: ❌ 여전히 실패

---

### 시도 3: Symlink 대신 실제 파일 복사

**가설**: Let's Encrypt가 생성한 symlink를 Docker가 따라가지 못하는 것이다.

**조치**:
```bash
# Let's Encrypt 구조
/etc/letsencrypt/
├── live/ddoksori.duckdns.org/
│   ├── fullchain.pem -> ../../archive/.../fullchain1.pem  # symlink
│   └── privkey.pem -> ../../archive/.../privkey1.pem      # symlink
└── archive/ddoksori.duckdns.org/
    ├── fullchain1.pem  # 실제 파일
    └── privkey1.pem    # 실제 파일

# symlink 제거하고 실제 파일 복사
sudo rm /etc/letsencrypt/live/ddoksori.duckdns.org/*.pem
sudo cp /etc/letsencrypt/archive/ddoksori.duckdns.org/fullchain1.pem \
        /etc/letsencrypt/live/ddoksori.duckdns.org/fullchain.pem
sudo cp /etc/letsencrypt/archive/ddoksori.duckdns.org/privkey1.pem \
        /etc/letsencrypt/live/ddoksori.duckdns.org/privkey.pem
```

**결과**: ❌ 여전히 실패

---

### 시도 4: 체계적인 디버깅

**접근 방식**: 문제를 격리하여 원인 파악

#### 테스트 1: Alpine 컨테이너에서 인증서 접근
```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt:ro alpine \
  ls -la /etc/letsencrypt/live/ddoksori.duckdns.org/
```
**결과**: ✅ 파일 정상 조회됨

#### 테스트 2: nginx:alpine 컨테이너에서 인증서 접근
```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt:ro nginx:alpine \
  ls -la /etc/letsencrypt/live/ddoksori.duckdns.org/
```
**결과**: ✅ 파일 정상 조회됨

#### 테스트 3: ECR 이미지에서 인증서 접근
```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt:ro \
  $ECR_REGISTRY/ddoksori-frontend:latest \
  ls -la /etc/letsencrypt/live/ddoksori.duckdns.org/
```
**결과**: ✅ 파일 정상 조회됨

#### 테스트 4: ECR 이미지에서 nginx config 테스트
```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt:ro \
  $ECR_REGISTRY/ddoksori-frontend:latest \
  nginx -t
```
**결과**: ✅ 성공 (다른 에러: "host not found in upstream 'backend'" - 네트워크 없어서 정상)

**핵심 발견**:
> **수동으로 실행하면 인증서 마운트가 정상 동작한다!**
> **문제는 docker-compose로 실행할 때만 발생한다.**

---

### 시도 5: 서버의 docker-compose.prod.yml 확인

```bash
cat /home/ubuntu/<app>/docker-compose.prod.yml
```

**발견**:
```yaml
# 서버에 있던 구버전 docker-compose.prod.yml
frontend:
  image: ${ECR_REGISTRY}/ddoksori-frontend:latest
  ports:
    - "80:80"
  # volumes 섹션이 없음! ← 문제의 원인
```

**Repository의 최신 버전**:
```yaml
# GitHub Repository의 docker-compose.prod.yml
frontend:
  image: ${ECR_REGISTRY}/ddoksori-frontend:latest
  ports:
    - "80:80"
    - "443:443"  # ← 누락됨
  volumes:
    - /etc/letsencrypt:/etc/letsencrypt:ro  # ← 누락됨
    - /var/www/certbot:/var/www/certbot:ro  # ← 누락됨
```

---

## 근본 원인

### CI/CD의 배포 방식 문제

```
CI/CD Pipeline:
1. Docker 이미지 빌드 → ECR Push ✅
2. EC2에서 docker pull ✅
3. docker-compose up ✅
4. ❌ docker-compose.prod.yml은 동기화하지 않음
```

**문제점**:
- EC2 서버는 Git repository가 아님 (`git pull` 불가)
- CI/CD는 Docker 이미지만 배포하고, 설정 파일(docker-compose.prod.yml)은 배포하지 않음
- 서버의 `docker-compose.prod.yml`이 SSL 볼륨 마운트가 추가되기 전 버전으로 고정됨

### 왜 이전에는 문제가 없었나?

| 시점 | docker-compose.prod.yml 상태 | 결과 |
|------|------------------------------|------|
| SSL 추가 전 | volumes 없음 | 정상 (HTTP만 사용) |
| SSL 추가 후 (서버) | volumes 없음 (구버전) | 실패 |
| SSL 추가 후 (Repository) | volumes 있음 (신버전) | - |

---

## 해결 방법

### 최종 해결: CI/CD에 설정 파일 동기화 추가

`.github/workflows/deploy-staging.yml` 수정:

```yaml
- name: Deploy to Staging
  uses: appleboy/ssh-action@v1.0.0
  with:
    script: |
      # ... ECR 로그인 후 ...

      # 설정 파일 동기화 (GitHub에서 최신 버전 다운로드)
      echo "Syncing docker-compose.prod.yml from GitHub..."
      curl -sf -o docker-compose.prod.yml.new \
        https://raw.githubusercontent.com/SKN19-FINAL-5team/LLM/main/docker-compose.prod.yml
      if [ -f docker-compose.prod.yml.new ]; then
        mv docker-compose.prod.yml.new docker-compose.prod.yml
        echo "docker-compose.prod.yml updated successfully"
      else
        echo "WARNING: Failed to download docker-compose.prod.yml, using existing file"
      fi

      # 이미지 Pull 및 배포
      docker compose -f docker-compose.prod.yml pull
      docker compose -f docker-compose.prod.yml up -d
```

### 해결 후 배포 흐름

```
CI/CD Pipeline (수정 후):
1. Docker 이미지 빌드 → ECR Push ✅
2. EC2 SSH 접속 ✅
3. GitHub에서 docker-compose.prod.yml 다운로드 ✅ (NEW!)
4. docker pull ✅
5. docker-compose up ✅
6. Health check ✅
```

---

## 예방 조치

### 1. 설정 파일 변경 시 체크리스트

- [ ] `docker-compose.prod.yml` 변경 시 CI/CD 워크플로우 확인
- [ ] 새로운 볼륨 마운트 추가 시 서버에 해당 디렉토리 존재 여부 확인
- [ ] 포트 추가 시 보안 그룹(Security Group) 확인

### 2. 디버깅 순서

SSL/인증서 관련 문제 발생 시:

1. **인증서 파일 존재 확인**
   ```bash
   ls -la /etc/letsencrypt/live/도메인/
   ```

2. **Docker에서 볼륨 마운트 확인**
   ```bash
   docker run --rm -v /etc/letsencrypt:/etc/letsencrypt:ro alpine ls -la /etc/letsencrypt/live/
   ```

3. **docker-compose.yml에 볼륨 정의 확인**
   ```bash
   grep -A5 "volumes:" docker-compose.prod.yml
   ```

4. **서버와 Repository의 설정 파일 비교**
   ```bash
   diff <(curl -s https://raw.githubusercontent.com/.../docker-compose.prod.yml) docker-compose.prod.yml
   ```

### 3. 모니터링 추가 권장

```yaml
# 향후 추가 고려사항
- name: Verify Config Sync
  run: |
    # 서버의 docker-compose.prod.yml 해시와 Repository 해시 비교
    SERVER_HASH=$(ssh ... "md5sum docker-compose.prod.yml | cut -d' ' -f1")
    REPO_HASH=$(curl -s ... | md5sum | cut -d' ' -f1)
    if [ "$SERVER_HASH" != "$REPO_HASH" ]; then
      echo "WARNING: Config file mismatch!"
    fi
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `.github/workflows/deploy-staging.yml` | 배포 워크플로우 (수정됨) |
| `docker-compose.prod.yml` | 프로덕션 Docker Compose 설정 |
| `frontend/nginx.conf` | nginx 설정 (HTTP health check 추가됨) |
| `frontend/Dockerfile.prod` | 프론트엔드 Docker 이미지 빌드 |

---

## 교훈

1. **CI/CD는 코드만 배포하는 것이 아니다** - 설정 파일도 동기화 전략이 필요하다
2. **수동 테스트와 자동 배포의 차이를 인식하라** - 수동으로 되는데 CI/CD에서 안 되면 환경 차이를 의심
3. **체계적인 디버깅이 시간을 절약한다** - 무작정 시도하지 말고 문제를 격리하여 테스트
4. **서버 상태를 Git으로 관리하거나, 배포 시 동기화하라** - 설정 드리프트(drift) 방지

---

## 참고 자료

- [Let's Encrypt 인증서 구조](https://letsencrypt.org/docs/certificates/)
- [Docker Volume 권한 문제](https://docs.docker.com/storage/volumes/)
- [GitHub Actions SSH 배포](https://github.com/appleboy/ssh-action)
