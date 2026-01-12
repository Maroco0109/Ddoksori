# DBeaver (Windows) ↔ WSL2 PostgreSQL 연결 가이드

Windows 환경의 DBeaver에서 WSL2 내부의 Docker 컨테이너로 실행 중인 PostgreSQL에 접속하는 방법입니다.

## 1. 사전 준비

- **WSL2** 설치 및 실행 중
- **Docker Desktop** (WSL2 backend) 실행 중
- `docker-compose up`으로 PostgreSQL 컨테이너 실행 중 (`ddoksori_db`)

## 2. 접속 정보 확인

`docker-compose.yml` 설정에 따르면, PostgreSQL은 **5432** 포트를 호스트에 노출하고 있습니다.

- **Host**: `localhost` (Docker Desktop이 포트 포워딩을 자동으로 처리함)
- **Port**: `5432`
- **Database**: `ddoksori`
- **Username**: `postgres`
- **Password**: `postgres` (기본값)
- **Driver**: `PostgreSQL`

## 3. DBeaver 연결 설정

1.  DBeaver 실행 → 좌측 상단 **"새 데이터베이스 연결" (플러그 아이콘)** 클릭
2.  **PostgreSQL** 선택 → **다음(Next)**
3.  **General** 탭 설정:
    - **Host**: `localhost`
    - **Port**: `5432`
    - **Database**: `ddoksori`
    - **Username**: `postgres`
    - **Password**: `postgres`
4.  **Test Connection (연결 테스트)** 클릭
    - "Connected" 메시지가 나오면 성공입니다.
5.  **완료(Finish)**

> [!TIP]
> 만약 `localhost`로 접속이 안 된다면, WSL2의 IP 주소를 직접 입력해야 할 수도 있습니다.
> WSL2 터미널에서 `ip addr show eth0` 명령어로 IP를 확인하세요. (보통 `172.x.x.x`)

## 4. CloudBeaver 사용하기 (웹 브라우저)

본 리포지토리에는 웹 기반 DB 관리 도구인 **CloudBeaver**가 포함되어 있습니다. 별도 설치 없이 브라우저에서 바로 DB를 확인할 수 있습니다.

1.  컨테이너 실행: `docker-compose up -d cloudbeaver`
2.  브라우저 접속: [http://localhost:8978](http://localhost:8978)
3.  초기 설정:
    - 관리자 계정 생성 (Admin / Password 설정)
4.  새 연결 생성:
    - **PostgreSQL** 선택
    - **Host**: `db` (Docker 네트워크 내부 호스트명)
    - **Port**: `5432`
    - **Database**: `ddoksori`
    - **User/Password**: `postgres` / `postgres`
