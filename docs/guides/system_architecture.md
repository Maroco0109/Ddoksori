# 시스템 아키텍처 (System Architecture)

본 문서는 '똑소리' 프로젝트의 **데이터 관리, 인프라 구조, Multi-Agent System (MAS)** 설계를 시각화한 자료입니다.

## 1. 데이터 관리 파이프라인 (Data Pipeline)

법령(API), 상담사례(Web), 분쟁조정사례/기준(PDF)의 수집 및 가공 흐름입니다.

```mermaid
flowchart TD
    %% 스타일 정의
    classDef source fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef external fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef process fill:#fff8e1,stroke:#fbc02d,stroke-width:2px;
    classDef db fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef ai fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    subgraph Data_Sources [1. 데이터 원천]
        D_Law["법령 규정 - National Law API"]:::source
        D_Web["상담사례 - Consumer Web Crawling"]:::source
        D_Case["분쟁조정사례 - PDF HWP Files"]:::source
        D_Std["분쟁조정기준 - PDF HWP Files"]:::source
    end

    subgraph Extraction [2. 추출 및 구조화]
        E_API["XML Response - Hierarchy Parsing"]:::process
        E_Crawl["Web Data Parsing - HTML Text"]:::process
        E_Upstage["Upstage Doc Parsing API - OCR and Layout Analysis"]:::external
        
        E_JSON1["JSONL 변환 - 분쟁조정사례"]:::process
        E_JSON2["JSON 계층화 - 분쟁조정기준 별표 지침"]:::process
    end

    subgraph Ingestion [3. 적재 및 임베딩]
        I_Chunk["Semantic Chunking"]:::process
        I_Embed["Vector Embedding - RunPod KURE v1"]:::ai
    end

    subgraph Storage [4. 데이터베이스 PostgreSQL]
        %% 벡터 저장소
        DB_Vector[("pgvector - Vector Store")]:::db
        
        %% 정형 데이터 (Hierarchy)
        DB_Rel[("Relational Tables - Hierarchy Structure")]:::db
    end
    
    %% 흐름 연결: 법령
    D_Law -->|API Call| E_API
    E_API -->|계층 파싱| DB_Rel
    E_API -->|텍스트| I_Chunk

    %% 흐름 연결: 상담사례
    D_Web -->|Crawling| E_Crawl
    E_Crawl -->|텍스트| I_Chunk

    %% 흐름 연결: 분쟁조정사례 (PDF)
    D_Case -->|Upload| E_Upstage
    E_Upstage -->|Case Data| E_JSON1
    E_JSON1 -->|텍스트| I_Chunk

    %% 흐름 연결: 분쟁조정기준 (PDF)
    D_Std -->|Upload| E_Upstage
    E_Upstage -->|Standard Data| E_JSON2
    E_JSON2 -->|계층 구조| DB_Rel
    E_JSON2 -->|텍스트| I_Chunk

    %% 공통 임베딩 및 저장
    I_Chunk --> I_Embed
    I_Embed --> DB_Vector

    %% 테이블 매핑 설명
    DB_Rel -.->|"law_node criteria_units"| DB_Rel
    DB_Vector -.->|"chunks 1024d"| DB_Vector
```

## 2. Frontend - Backend 인프라 구조

오케스트레이터의 라우팅 모델(Small LLM)과 검색 모델(SPLADE)을 활용하는 하이브리드 인프라입니다.

```mermaid
graph TB
    %% 스타일 정의
    classDef user fill:#ffffff,stroke:#333,stroke-width:2px;
    classDef frontend fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef backend fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    classDef agent fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#333;
    classDef resource fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,stroke-dasharray: 5 5;

    %% 1. 사용자 및 프론트엔드
    User([사용자 User]):::user
    
    subgraph Frontend_Layer [Frontend Layer]
        Browser["Chrome Browser (Client)"]:::frontend
        ReactApp["React / Vite App"]:::frontend
    end

    %% 2. 백엔드 인프라 (에러 수정 지점)
    subgraph Backend_Infrastructure [Backend Server - EC2]
        Nginx["Nginx Reverse Proxy"]:::backend
        Uvicorn["Uvicorn ASGI Server"]:::backend
        FastAPI["FastAPI App Container"]:::backend
        
        %% 3. LangGraph 논리적 아키텍처
        subgraph LangGraph_System [LangGraph MAS]
            direction TB
            OrchAgent["Orchestrator Agent<br/>(Supervisor)"]:::agent
            
            RouterAgent["질의 분석 에이전트<br/>(Intent Analysis)"]:::agent
            RetrieverAgent["검색 에이전트<br/>(RAG Pipeline)"]:::agent
            GeneratorAgent["답변 생성 에이전트<br/>(Answer Draft)"]:::agent
            ReviewerAgent["답변 검토 에이전트<br/>(Answer Check)"]:::agent
            
            %% Agent 연결
            OrchAgent -- "1. 의도파악" --> RouterAgent
            OrchAgent -- "2. 검색요청" --> RetrieverAgent
            OrchAgent -- "3. 답변생성" --> GeneratorAgent
            OrchAgent -- "4. 검토요청" --> ReviewerAgent
            
            %% Feedback Loops
            RouterAgent -.->|"결과반환"| OrchAgent
            RetrieverAgent -.->|"Context"| OrchAgent
            GeneratorAgent -.->|"Draft"| OrchAgent
            ReviewerAgent -.->|"Approved"| OrchAgent
        end
    end

    %% 4. 외부 리소스 및 모델
    subgraph External_Resources [Model & Data Resources]
        SmallLLM["RunPod: Small LLM<br/>(Llama 3 8B / Qwen 2.5)"]:::resource
        SpladeModel["RunPod: SPLADE<br/>(Sparse Embedding)"]:::resource
        BigLLM["API: Big LLM<br/>(GPT-4o)"]:::resource
        VectorDB[("PostgreSQL<br/>pgvector")]:::resource
    end

    %% 흐름 연결
    User --> Browser
    Browser --> ReactApp
    ReactApp -->|"REST API"| Nginx
    Nginx -->|"Proxy Pass"| Uvicorn
    Uvicorn -->|"ASGI"| FastAPI
    FastAPI -->|"Request"| OrchAgent
    OrchAgent -->|"Response"| FastAPI

    %% 리소스 사용 관계
    RouterAgent -.->|"API Call"| SmallLLM
    RetrieverAgent -.->|"Embedding"| SpladeModel
    RetrieverAgent -.->|"Query"| VectorDB
    GeneratorAgent -.->|"Prompt"| BigLLM
    ReviewerAgent -.->|"Review"| BigLLM

```

## 3. Backend MAS (Multi-Agent System) 상세 로직

오케스트레이터가 Small Model을 사용하여 능동적으로 라우팅(일상대화 vs 전문상담)하는 흐름입니다.

```mermaid
sequenceDiagram
    participant U as User
    participant Orch as Orchestrator (LangGraph)
    participant SM as Small Model (RunPod)
    participant IR as Retrieval Agent
    participant AG as Answer Agent (Big Model)
    participant REV as Review Agent (Big Model)

    U->>Orch: 사용자 입력

    %% Phase 1: 오케스트레이터의 판단 (Router)
    rect rgb(235, 255, 235)
        Note over Orch, SM: [Supervision] 입력 의도 판단
        Orch->>SM: "이 입력이 일상 대화야, 전문 질문이야?"
        SM-->>Orch: {type: "general_chat" | "legal_query"}
    end

    alt 일상 대화 (General Chat)
        Orch->>SM: 가볍게 맞장구치는 답변 생성해줘
        SM-->>Orch: 일상 답변 (ex: "안녕하세요! 무엇을 도와드릴까요?")
        Orch->>U: 답변 전송 (종료)
    
    else 전문 질문 (Legal/Dispute Query)
        %% Phase 2: 질의 분석 (필요시 SM 재사용)
        Orch->>SM: 키워드 추출 및 의도 상세 분석
        SM-->>Orch: {keywords: [...], intent: "refund"}

        %% Phase 3: 정보 검색
        rect rgb(255, 250, 230)
            Orch->>IR: 검색 실행 (Code+SPLADE)
            IR-->>Orch: 근거 문서 (Context)
        end

        %% Phase 4: 답변 생성
        rect rgb(230, 240, 255)
            Orch->>AG: 전문 답변 생성 요청
            AG-->>Orch: 답변 초안
        end

        %% Phase 5: 검토
        rect rgb(255, 235, 238)
            Orch->>REV: 법률적 검토 요청
            REV-->>Orch: 승인
        end
        
        Orch->>U: 최종 답변 전송
    end
```
