# RunPod vLLM Setup Guide — EXAONE 4.5-33B

DDOKSORI의 M2 canonical RunPod 추론 모델인 **EXAONE 4.5-33B**(`LGAI-EXAONE/EXAONE-4.5-33B`)를
RunPod GPU Pod에서 vLLM(OpenAI-compatible)으로 서빙하고, 로컬 백엔드와 연결해 health/추론을
확인하는 절차를 설명한다.

> **최종 업데이트**: 2026-06-23 (H100 80GB ×1에서 실제 standup 성공 — 그 경로/플래그/함정 반영)
>
> 이전 1.2B(EXAONE 4.0-1.2B, :19010) 절차는 deprecated다. canonical env는 `EXAONE_RUNPOD_URL`,
> 대상 모델은 EXAONE 4.5-33B로 통일한다(M2-2 결정). 과거 문서가 참조하던
> `scripts/runpod/*.sh`는 repo에 존재하지 않으므로, 본 문서는 인라인 명령을 사용한다.

---

## 0. 요약 (한눈에)

| 단계 | 위치 | 핵심 |
| --- | --- | --- |
| 1. 모델 구동 | RunPod Pod | 커스텀 vLLM 포크 설치 → `vllm serve ... --tensor-parallel-size <GPU 장수>` (Pod 내부 :8000) |
| 2. 로컬 연결 | 로컬 | SSH 터널 `19080→8000` → `EXAONE_RUNPOD_URL=http://localhost:19080/v1` |
| 3. 연결 확인 | 로컬 | `python backend/scripts/testing/llm/check_vllm_health.py` (exit 0 = healthy) |

> ⚠️ **비용 주의**: EXAONE 4.5-33B는 80GB GPU 1장(A100-80GB/H100/H200) 또는 다중 GPU가 필요하다.
> RunPod balance가 테스트용($180 수준)이므로 **상시 가동하지 말고** 측정/테스트가 끝나면 Pod를
> **Stop**(Terminate 아님)해 과금을 멈춘다. Stop은 GPU 과금만 멈추고 설치물/가중치는 디스크에 남는다.

---

## 1. RunPod 환경에서 모델 다운로드 + 구동

### 1.1 Pod 배포

1. [RunPod](https://www.runpod.io/) 로그인 → **Pods** → **+ Deploy**.
2. GPU 선택 (33B BF16 가중치 ~66GB 기준):
   - **단일 80GB 1장**(A100-80GB / H100 / H200): 한 장에 들어감 → `--tensor-parallel-size 1`
   - **여러 장**(예: A100-40GB ×4): tensor-parallel → 장수에 맞춰 `--tensor-parallel-size N`
   - ⚠️ **GPU 장수 = `--tensor-parallel-size` 값**이어야 한다. 1장인데 TP=2면 구동 실패.
3. 템플릿: **RunPod PyTorch**(최신, CUDA 12.8+) 또는 vLLM 전용 템플릿. 템플릿 PyTorch **버전 자체는
   중요하지 않다** — §1.2에서 vllm 포크 설치 시 pip이 torch를 최신(cu130 등)으로 덮어쓰기 때문이다.
4. ⚠️ **호스트 드라이버 CUDA 필터링(가장 중요)**: RunPod은 GPU별로 호스트 드라이버 CUDA 버전이 다르다.
   필터 없이 배포하면 옛 드라이버(예: 12.4) 호스트에 걸려, 설치된 torch/vllm(CUDA 12.8~13.0 요구)이
   런타임에 `undefined symbol: cuMemcpyBatchAsync` 류로 깨진다.
   - 배포 화면에서 **"Additional filters" → "CUDA Versions"** 드롭다운을 열어 **12.8 이상**(이상적으로
     **13.0**) 호스트만 받도록 체크한다. fork의 torch가 cu130이므로 **13.0 호스트가 가장 안전**하다.
5. **디스크 배분(중요)**: RunPod 디스크는 2종류이고, **각각 어디에 쓰이는지가 다르다.**
   - **Container Disk** (`/`): `pip install` 패키지(`/usr/local/lib/.../dist-packages`), HF 캐시 기본 위치.
     기본값이 **20GB로 작아** torch+vllm(~10–15GB)만으로도 `No space left on device`가 난다.
   - **Volume Disk** (`/workspace`): 영구 저장용. 보통 여기에 큰 용량(120GB+)을 잡는다.
   - **권장 A**: Container Disk를 **≥ 100GB**로 잡으면 패키지+가중치가 전부 `/`에 들어가 단순하다.
   - **권장 B(볼륨만 큰 경우)**: Container Disk가 작고 Volume(`/workspace`)만 크면, §1.2의 "설치 위치"
     단계처럼 **venv와 HF 캐시를 `/workspace`로 보내** 120GB 볼륨에 설치한다(재배포 불필요).
6. SSH 접근용 공개키는 **Deploy 전에** RunPod **Settings → SSH Public Keys**에 등록한다.
   - ⚠️ RunPod은 계정 키를 **Pod 시작 시점에만** `authorized_keys`에 주입한다. Pod 생성 후 등록하거나
     생성과 거의 동시에 등록하면 **이미 뜬 Pod엔 키가 안 들어가** root 비밀번호를 묻게 된다(비번 없음=막힘).
     이 경우 Pod 재시작 없이 §2.1처럼 `authorized_keys`에 **수동 추가**한다.
7. **Deploy** 후 Pod의 `Connect` 패널에서 접속 정보를 확인한다(§2.1: 터널엔 **직접 TCP SSH** 필요).

> ✅ **배포 직후 1순위 확인 (설치 전에 반드시)**: 드라이버 CUDA가 torch CUDA보다 같거나 높아야 vLLM이
> 뜬다. GPU 드라이버는 **자기 버전 이하 CUDA만 실행**하기 때문이다(상위 버전 불가).
>
> ```bash
> nvidia-smi                                            # 우상단 "CUDA Version" = X (드라이버 지원 최대)
> python -c "import torch; print(torch.version.cuda)"   # = Y (torch가 빌드된 CUDA)
> ```
>
> **합격 기준: `X ≥ Y`**.
> - 예) `X=13.0, Y=13.0` → ✅ 통과 → §1.2 (A) precompiled로 바로 설치.
> - 예) `X=12.4, Y=13.0` → ❌ 불합격(드라이버가 낮음) → **무엇을 해도 깨진다.** 이 Pod를 Terminate하고
>   §1.1-4의 CUDA 필터로 **드라이버 ≥ 13.0 호스트**를 잡아 재배포한다.
> - 13.0 호스트를 못 구해 `X=12.8`까지만 가능하면, torch를 호스트에 맞춰 cu128로 내려야 한다(§1.2 참고,
>   버전 충돌이 잦아 비권장). **가장 확실한 건 CUDA 13.0 호스트 재배포**다.

### 1.2 의존성 설치 (Pod 내부)

먼저 Pod 내부 셸에 접근한다. **두 방법 중 하나만** 쓰면 된다.

- **(A) RunPod Web Terminal**: Pod의 `Connect → Web Terminal`을 열면 이미 Pod 내부다.
  아래 SSH 명령은 **실행하지 말고** 바로 포크 설치로 넘어간다.
- **(B) 로컬에서 SSH**: 로컬 PC 터미널에서 아래를 실행해 Pod로 접속한다(IP/포트/키는 본인 Pod 값).

```bash
# (B) 로컬 PC에서만 실행. Web Terminal 안에서는 실행하지 말 것(자기 자신에 접속 실패함).
# 키 파일명은 본인이 생성한 것으로(예: id_ed25519). Connect 패널의 "직접 TCP SSH" 명령을 쓴다(§2.1).
ssh root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519
```

> **Web Terminal이 자주 끊기면(Connection Closed)** 로컬 SSH가 안정적이다. 단, tmux 안의 빌드/서버는
> Web Terminal이 끊겨도 죽지 않으니, 재접속 후 `tmux attach -t vllm`로 복귀하면 된다.

**(설치 위치) Container Disk가 작으면 먼저 `/workspace` 볼륨에 venv를 만든다.** 
`df -h`로 `/`(Container Disk) 여유를 확인한다. 패키지(~10–15GB)+가중치(66GB)를 담기에 부족하면
(예: Container Disk 20GB), **120GB Volume(`/workspace`)에 설치**한다. 그러면 재배포 없이 해결된다.

```bash
df -h                                    # / 와 /workspace 여유 확인
python -m venv /workspace/venv           # 볼륨에 venv 생성
source /workspace/venv/bin/activate      # 활성화
which python                             # → /workspace/venv/bin/python 이면 OK
export HF_HOME=/workspace/hf             # 가중치(66GB)도 볼륨에 받게 함(serve 때 OOM 방지)
```

> **매 세션 활성화 필요**: venv와 `HF_HOME`은 새 셸/tmux마다 다시 잡아야 한다. 자동화하려면:
> ```bash
> echo 'source /workspace/venv/bin/activate' >> ~/.bashrc
> echo 'export HF_HOME=/workspace/hf' >> ~/.bashrc
> ```
> Container Disk가 충분(≥100GB)하면 이 venv 단계는 생략하고 시스템 파이썬에 바로 설치해도 된다.

EXAONE 4.5-33B는 **표준 vLLM로는 서빙되지 않으며** 커스텀 포크가 필요하다.

**(A) precompiled — 검증된 권장 경로.** 단, **§1.1의 `X(드라이버 CUDA) ≥ Y(torch CUDA)` 가 충족된
호스트**에서만 동작한다(이 standup은 드라이버 CUDA 13.0 H100 호스트에서 성공). precompiled 휠은 최신
CUDA(12.8~13.0)로 빌드돼 있어, 드라이버가 낮으면 import 시 `undefined symbol: cuMemcpyBatchAsync`로 깨진다.

```bash
# flash-attn CUDA 커널을 직접 빌드하지 않고 미리 빌드된 걸 받음(빠르고 OOM 없음)
VLLM_USE_PRECOMPILED=1 pip install git+https://github.com/lkm2835/vllm.git@add-exaone4_5
```

**transformers 포크(순수 파이썬이라 컴파일 없이 금방 설치)**

```bash
pip install git+https://github.com/nuxlear/transformers.git@add-exaone4_5-v5.3.0.dev0
```

> ⚠️ **소스 빌드는 `undefined symbol` 해결책이 아니다(이 세션에서 직접 확인)**: 드라이버가 낮을 때
> `pip uninstall -y vllm` 후 소스 빌드(`MAX_JOBS=32 pip install git+...`)를 해도, pip이 설치한 **torch가
> cu130**이면 빌드 결과물이 여전히 13.0 드라이버 심볼을 참조해 **똑같이 깨진다.** 근본 해결은
> **§1.1-4의 CUDA 필터로 드라이버 ≥ torch CUDA 호스트에 재배포**하는 것이다. 정말로 낮은 드라이버
> 호스트에 묶여 있다면 torch를 드라이버에 맞춰 cuXXX로 내린 뒤 소스 빌드해야 하는데 버전 충돌이 잦아
> 권하지 않는다. (소스 빌드 시 `MAX_JOBS` 주의: flash-attn 컴파일이 무거워 코어 수만큼 병렬이면 RAM이
> 터져 `FAILED: [code=137]`(SIGKILL). `MAX_JOBS`로 32~64, RAM 빠듯하면 1~2로 제한.)

> compressed-tensors/vllm가 `transformers<5`를 요구한다는 pip 경고는 **정상**이다. EXAONE 4.5는
> transformers 5.x 포크가 필요하고, vLLM 포크가 이에 맞춰 패치돼 있다. 다운그레이드하지 말 것.

> `uv`를 쓰려면 Pod 내부에선 가상환경 없이 시스템 파이썬에 설치해야 하므로 **`--system`이 필수**다
> (없으면 `No virtual environment found` 에러). 예: `uv pip install --system git+...`.

> 설치 검증: `python -c "import vllm, transformers; print(vllm.__version__, transformers.__version__)"`

> **FastAPI 0.137 호환 핀(필수)**: 설치 시 FastAPI가 0.137+로 들어가면, 서버 구동 후 **모든 요청이
> 500**(`AttributeError: '_IncludedRouter' object has no attribute 'path'`)으로 깨진다. FastAPI 0.137이
> `app.routes` 구조를 바꿔 vLLM의 prometheus 계측이 `route.path`를 못 읽기 때문이다. 설치 직후 내려둔다:
> ```bash
> pip install "fastapi<0.137"     # 예: fastapi==0.136.0
> python -c "import fastapi; print(fastapi.__version__)"   # 0.136.x 확인
> ```
> 이미 서버가 떠 있었다면 이 변경은 **프로세스를 재시작해야** 적용된다(`pkill -f "vllm serve"` 후 재구동).

> Hugging Face gated 모델일 경우 `huggingface-cli login` 또는 `export HF_TOKEN=...`가 필요할 수 있다.

### 1.3 vLLM 서버 구동 (Pod 내부)

> ⚠️ **tmux 안에서 실행 필수**: Web Terminal에서 포그라운드로 띄운 프로세스는 탭을 닫거나
> 새로고침하면 SIGHUP으로 죽는다. vLLM 서버는 반드시 `tmux`(또는 `nohup`) 안에서 실행해
> 세션이 끊겨도 살아남게 한다. 단순 pip 설치물은 디스크에 남지만, **실행 중인 서버는 남지 않는다.**
>
> ```bash
> apt-get update && apt-get install -y tmux   # tmux 미설치 시
> tmux new -s vllm                            # vllm 세션 시작 → 이 안에서 아래 vllm serve 실행
> # 분리: Ctrl+b 누른 뒤 d  (탭을 닫아도 서버 유지)
> # 재접속: tmux attach -t vllm
> ```

아래는 **단일 80GB GPU(H100/H200/A100-80GB ×1)에서 실제 구동에 성공한 구성**이다(`Application startup
complete` 확인됨). 터미널 붙여넣기 시 백슬래시 줄바꿈이 깨지는 일이 잦으니 **한 줄로** 실행한다.

```bash
VLLM_USE_DEEP_GEMM=0 vllm serve LGAI-EXAONE/EXAONE-4.5-33B --served-model-name LGAI-EXAONE/EXAONE-4.5-33B --port 8000 --tensor-parallel-size 1 --max-model-len 8192 --gpu-memory-utilization 0.95 --enforce-eager --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser hermes --limit-mm-per-prompt '{"image": 64}' --speculative_config '{"method": "mtp", "num_speculative_tokens": 3}'
```

- 최초 구동 시 Hugging Face에서 가중치를 다운로드한다(수 분~수십 분).
- `Application startup complete` / `Uvicorn running on http://0.0.0.0:8000` 로그가 뜨면 준비 완료.

단일 80GB GPU에서 검증된 핵심 플래그(이 순서로 메모리·커널 장벽을 넘었다):

| 플래그 | 이유 |
| --- | --- |
| `--tensor-parallel-size 1` | GPU 장수와 같아야 한다(1장→1, 4장→4). 불일치 시 구동 실패 |
| `--max-model-len 8192` | 가중치 ~66GB 후 KV 캐시 여유가 적어 32768은 `ValueError: ... KV cache memory` 로 실패. 8192면 통과(측정엔 충분). 더 부족하면 `4096` |
| `--gpu-memory-utilization 0.95` | 기본 0.9→0.95로 KV 캐시 예산 확보(80GB 한 장에서 필수에 가까움) |
| `--enforce-eager` | CUDA graph 캡처를 꺼 그 메모리를 KV 캐시로 돌림. 성능 graph는 측정 이후 따로 비교 |
| `VLLM_USE_DEEP_GEMM=0` | 워밍업의 FP8 DeepGEMM 경로가 `RuntimeError: DeepGEMM backend is not available`로 실패할 때 우회. **H100/H200이면** `pip install -U deep_gemm`으로 FP8 커널을 켜 성능을 올릴 수도 있다(개선판 측정 항목) |

> ⚠️ **붙여넣기 잘림**: 백슬래시 멀티라인을 붙여넣다 `--served-model-name: expected at least one
> argument` 류로 끊기면, 셸이 다음 줄을 기다리는 것(`>`)이다. `Ctrl+C` 후 위 **한 줄 버전**으로 재실행.

> **정합성 규칙**: `--served-model-name` 값은 로컬 `.env`의 `EXAONE_MODEL`과 **반드시 동일**해야
> 추론(`/v1/chat/completions`)이 동작한다. 본 문서는 양쪽 모두 `LGAI-EXAONE/EXAONE-4.5-33B`로 맞춘다.
> (HF 모델 카드 예시는 짧은 별칭 `EXAONE-4.5-33B`를 쓰므로, 별칭을 쓰려면 `.env`도 동일하게 바꾼다.)

### 1.4 Pod 내부 1차 확인

서버가 뜬 같은 Pod에서:

```bash
curl http://localhost:8000/health        # 200 OK 면 liveness 정상
curl http://localhost:8000/v1/models      # data[0].id 에 모델명이 보이면 정상
```

---

## 2. 모델을 로컬 환경과 연결

vLLM은 Pod 내부 `:8000`에서 서빙된다. 로컬 백엔드의 canonical 포트는 `:19080`이다.

### 2.1 SSH 터널링 (로컬, 새 터미널)

RunPod **Connect 패널엔 SSH가 두 종류**다. 포트포워딩(`-L`)이 필요한 터널은 **직접 TCP SSH**(`root@<IP> -p
<PORT>`)를 써야 한다. 프록시(`<id>@ssh.runpod.io`)는 셸 접속용이라 `-L`이 보통 안 된다.

```bash
# 로컬 19080  ->  Pod 내부 8000  (직접 TCP SSH. 키 파일명은 본인 것으로)
ssh -N -L 19080:localhost:8000 root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519
```

- `-N`: 원격 명령 없이 터널만 유지. **붙으면 아무 출력 없이 커서만 깜빡이며 멈춘다 — 이게 성공 신호다.**
  이 터미널은 닫지 말고 두고, **다른 로컬 터미널**에서 `curl http://localhost:19080/v1/models`로 확인한다.
- 연결 후 로컬에서 vLLM API가 `http://localhost:19080/v1`로 노출된다.

> ⚠️ **터널 끊김 방지 (필수에 가까움)**: 기본 `ssh -N -L` 터널은 **유휴·네트워크 변동·로컬 슬립**으로
> 시간이 지나면 **조용히 끊긴다.** 이때 pod의 vLLM(tmux)은 멀쩡한데 **로컬 터널만 죽어**
> `localhost:19080`이 `http_code=000`(연결 실패)이 된다 — "모델이 멈춘 것처럼" 보이지만 실제로는
> 오래된 터널 세션이 죽은 것이다. 측정 배치가 도는 도중 끊기면 클라이언트가 연결 대기로 **hang**한다.
> keepalive 옵션으로 띄우고, 배치 중에는 그 세션을 닫지 않는다:
> ```bash
> # keepalive(30s마다 ping, 3회 실패 시 정리) + 백그라운드(-f)
> ssh -f -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 19080:localhost:8000 root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519
> ```
> 그래도 자주 끊기면 **`autossh`**(자동 재연결)를 쓰거나, 아래 **RunPod Proxy URL**(터널 자체가 없어 끊길
> 게 없음)로 전환한다. 측정 직전 `curl http://localhost:19080/v1/models`로 살아있는지 항상 먼저 확인.

> **root 비밀번호를 물으면** 키 인증 실패다(RunPod root Pod는 비번이 없어 막힘). 원인은 보통 **키 미주입**
> (§1.1-6 타이밍). Pod 셸(Web Terminal)에서 로컬 공개키(`cat ~/.ssh/id_ed25519.pub`)를 직접 넣는다:
> ```bash
> mkdir -p ~/.ssh && chmod 700 ~/.ssh
> echo "<로컬_공개키_한줄>" > ~/.ssh/authorized_keys   # > 는 옛 키 제거+교체, >> 는 추가
> chmod 600 ~/.ssh/authorized_keys
> ```
> 다음에 Pod을 **새로** 팔 때는 키가 이미 계정에 있어 자동 주입되므로 이 작업이 필요 없다.

> **대안 (RunPod Proxy URL, SSH 불필요)**: Connect 패널의 **Port 8000 HTTP Service** URL
> `https://<pod-id>-8000.proxy.runpod.net`을 쓰면 터널·키 없이 바로 붙는다. 이 경우 `EXAONE_RUNPOD_URL`에
> `https://<pod-id>-8000.proxy.runpod.net/v1`을 넣고 SSH 터널은 생략한다(8000이 HTTP 포트로 노출돼 있어야 함).

### 2.2 로컬 `.env` 설정

`.env`(템플릿은 `.env.example`)에 canonical 값을 설정한다.

```env
EXAONE_RUNPOD_URL=http://localhost:19080/v1
EXAONE_RUNPOD_API_KEY=dummy
EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B
EXAONE_MODEL_SIZE=33B
EXAONE_TIMEOUT=10
```

> Proxy URL을 쓰면 `EXAONE_RUNPOD_URL`만 그 값으로 교체한다.

---

## 3. 연결 확인 (헬스 체크 + 테스트)

### 3.1 로컬에서 직접 probe

```bash
# /v1/models — 모델 id 확인
curl http://localhost:19080/v1/models

# /health — vLLM liveness
curl http://localhost:19080/health
```

### 3.2 프로젝트 health 스크립트 (권장, 재현 가능)

`EXAONE_RUNPOD_URL`을 읽어 provider/model/url/latency를 JSON으로 출력한다. 종료코드 0이면 healthy.

```bash
# .env 로딩 환경(예: docker compose 또는 export)에서
python backend/scripts/testing/llm/check_vllm_health.py

# 또는 URL을 직접 지정
python backend/scripts/testing/llm/check_vllm_health.py --url http://localhost:19080/v1
```

정상 출력 예:

```json
{
  "provider": "runpod_vllm",
  "url": "http://localhost:19080/v1",
  "model": "LGAI-EXAONE/EXAONE-4.5-33B",
  "status": "healthy",
  "http_status": 200,
  "latency_ms": 467.8,
  "vllm_health": true,
  "error_type": null
}
```

> 위 `latency_ms: 467.8`은 2026-06-23 H100 standup에서 실제 캡처한 M2-2 healthy 기준선 값이다(SSH 터널
> 경유). 네트워크/경유 방식(터널 vs Proxy)에 따라 값이 달라지므로, 측정 시 경유 방식도 함께 기록한다.

실패 시 `error_type`로 원인을 구분한다: `not_configured`(URL 미설정) / `connection_error`(터널 끊김·Pod 정지) / `timeout` / `bad_response`.

### 3.3 백엔드 API 경유 확인

백엔드(로컬 compose 등)가 떠 있으면:

```bash
curl http://localhost:8000/health/llm/exaone
# -> {"status":"healthy","provider":"runpod_vllm","url":...,"model":...,"latency_ms":...}
```

### 3.4 추론 스모크 테스트 (OpenAI 호환)

실제 생성이 되는지 확인한다. `model` 값은 `--served-model-name`/`EXAONE_MODEL`과 동일해야 한다.

> ⚠️ **반드시 한 줄로 복사**한다. 백슬래시 멀티라인이나 백틱이 끼면 셸이 `>`(다음 줄 대기) 상태로
> 멈춘다. 그 경우 `Ctrl+C`로 빠져나와 아래 **한 줄** 명령을 다시 붙여넣는다.

로컬(SSH 터널 `:19080`)에서:

```bash
curl http://localhost:19080/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"LGAI-EXAONE/EXAONE-4.5-33B","messages":[{"role":"user","content":"안녕하세요, 한 문장으로 자기소개 해주세요."}],"max_tokens":64}'
```

Pod 내부(`:8000`)에서 바로 확인할 때:

```bash
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"LGAI-EXAONE/EXAONE-4.5-33B","messages":[{"role":"user","content":"안녕하세요, 한 문장으로 자기소개 해주세요."}],"max_tokens":64}'
```

`choices[0].message.content`에 응답이 오면 end-to-end 연결 성공이다.

> ⚠️ **reasoning 모델 주의**: EXAONE 4.5는 답 이전에 `reasoning` 필드에 사고 과정을 먼저 쓴다.
> `max_tokens`가 작으면(예: 64) 토큰을 reasoning에 다 써 `finish_reason: "length"`로 끊기고
> **`content`가 `null`**로 나올 수 있다(정상, 버그 아님). 실제 답 문장을 보려면 `max_tokens`를 **512 이상**으로
> 올린다. 연결 자체는 `usage.completion_tokens`가 0보다 크면 정상 생성된 것이다.

> **한글 프롬프트가 붙여넣기에서 깨지면**(`applicati�` 등) 영어 프롬프트로 바꾸거나, body를 파일로 분리한다:
> `printf '%s' '<json>' > /tmp/req.json && curl ... -d @/tmp/req.json`

---

## 4. 측정 캡처 (M2-2 healthy 기준선)

healthy 상태에서 다음을 **bounded(수 회)**로 실행해 측정값을 기록한다(balance 보존).

```bash
python backend/scripts/testing/llm/check_vllm_health.py   # latency_ms, model 기록
```

- 기록 항목: `status`, `model`, `latency_ms`, `http_status`.
- 이 값이 M2-3 provider policy 결정과 M3 측정 시스템의 가용성 기준선이 된다.
- 측정이 끝나면 **RunPod Pod를 Stop**해 과금을 멈춘다.

---

## 5. Troubleshooting

| 증상 | 원인/조치 |
| --- | --- |
| `check_vllm_health.py`가 `connection_error` | SSH 터널이 끊겼거나 Pod/vLLM이 정지. 터널 재연결, vLLM 로그 확인 |
| `/v1/models`는 200인데 추론이 404/400 | `model` 값이 `--served-model-name`과 불일치. `EXAONE_MODEL`을 일치시킬 것 |
| OOM (구동 중 메모리 부족) | `--max-model-len` 축소, `--tensor-parallel-size` 증가, 더 큰 VRAM GPU 사용 |
| 가중치 다운로드 실패 | Pod 디스크 용량 확인(≥120GB), HF 토큰/네트워크 확인 |
| 표준 vLLM로 실행해 모델 로드 실패 | 반드시 `add-exaone4_5` 커스텀 포크 설치(§1.2) |
| 빌드 중 `FAILED: [code=137]` | flash-attn 컴파일 OOM(SIGKILL). `MAX_JOBS` 낮춰 재빌드(§1.2 B) 또는 `VLLM_USE_PRECOMPILED=1` |
| import 시 `undefined symbol: cuMemcpyBatchAsync`(_v2 포함) | 드라이버 CUDA < torch CUDA 불일치. `nvidia-smi`의 CUDA Version과 `torch.version.cuda` 비교(§1.1 배포 직후 확인). torch가 더 높으면 소스 빌드로도 안 고쳐짐 → CUDA 필터로 드라이버 높은 호스트에 재배포 |
| 구동 시 `--tensor-parallel-size` 관련 실패 | TP 값 ≠ GPU 장수. `nvidia-smi`로 장수 확인 후 일치(1장→1) |
| `No space left on device` (pip install 중) | Container Disk(`/`)가 작음(기본 20GB). `/workspace` 볼륨에 venv 설치(§1.2) 또는 Container Disk ≥100GB로 재배포 |
| `ValueError: ... KV cache memory` (init 단계) | 단일 80GB에서 max seq len이 너무 큼. `--max-model-len 8192`(또는 4096) + `--gpu-memory-utilization 0.95` + `--enforce-eager`(§1.3) |
| `RuntimeError: DeepGEMM backend is not available` (워밍업) | FP8 커널 워밍업 실패. `VLLM_USE_DEEP_GEMM=0`으로 우회. H100/H200이면 `pip install -U deep_gemm`으로 켤 수도 있음(§1.3) |
| `--served-model-name: expected at least one argument` | 백슬래시 멀티라인 붙여넣기가 잘림. `Ctrl+C` 후 한 줄 명령으로 재실행(§1.3) |
| 모든 요청 500 `'_IncludedRouter' object has no attribute 'path'` | FastAPI 0.137+ 비호환. `pip install "fastapi<0.137"` 후 **서버 프로세스 재시작**(§1.2). pip만 하고 재시작 안 하면 안 고쳐짐 |
| SSH가 **root 비밀번호**를 물음 | 키 인증 실패(비번 없음=막힘). 계정 키가 Pod 시작 후 등록돼 미주입된 경우가 많음. Pod 셸에서 `authorized_keys`에 공개키 수동 추가(§2.1) |
| `ssh -N`이 **커서만 깜빡이고 멈춤** | 정상(터널 성공). 창을 두고 **다른 터미널**에서 `curl localhost:19080/v1/models`로 확인(§2.1) |
| `Connection refused ... 19080` | 로컬 터널이 안 떴거나, 명령을 **Pod 안에서** 실행한 것. Pod 내부에선 `:8000`을 쓰고, 로컬에선 터널(§2.1)을 먼저 띄울 것 |
| 잘 되던 `:19080`이 갑자기 `http_code=000`(빈 응답/연결 실패), 측정 배치가 **hang** | **오래된 SSH 터널 세션이 죽음**(유휴·네트워크 변동). pod/vLLM(tmux)은 정상인데 로컬 터널만 끊긴 것. `ssh -N -L` 세션을 **새로** 띄우면 복구. 재발 방지는 keepalive 옵션(`-o ServerAliveInterval=30`)/`autossh`/Proxy URL(§2.1) |
| 추론 응답 `content: null` / `finish_reason: "length"` | reasoning 모델이 `max_tokens`를 사고에 다 씀. `max_tokens`를 512+로(§3.4). `completion_tokens>0`이면 생성 자체는 정상 |
| Web Terminal `Connection Closed` 잦음 | 로컬 직접 TCP SSH로 접속(§2.1). tmux 안의 빌드/서버는 끊겨도 살아있으니 `tmux attach -t vllm`로 복귀 |
| tmux에서 **마우스 휠 스크롤 안 됨** | 정상. `Ctrl+b` → `[` 로 copy mode 진입 후 PageUp/방향키로 스크롤, `q`로 종료 |
| `transformers<5` pip 경고 | 정상. EXAONE 4.5는 transformers 5.x 포크 필요. 다운그레이드 금지(§1.2) |

---

## 6. 참고

- 모델 카드: https://huggingface.co/LGAI-EXAONE/EXAONE-4.5-33B
- canonical env / health 도구 결정: `docs/plans/modules/M2-2-runpod-vllm-health-check-plan.md`
- 호출 경로 인벤토리: `docs/plans/modules/M2-1-llm-call-path-inventory.md`
