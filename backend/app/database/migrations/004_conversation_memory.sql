-- ============================================================
-- 004_conversation_memory.sql
-- 대화 메모리 및 인증 시스템 데이터베이스 스키마
--
-- 작성일: 2026-01-28
-- 설명: 대화 이력 저장, 요약 compaction, 사용자 인증 (OAuth)
--
-- ⚠️ 주의: 이 파일은 수동으로 실행되어야 합니다.
--          DB 계정이 READ_ONLY일 수 있으므로 권한 확인 후 실행하세요.
-- ============================================================

-- Enable pgcrypto extension for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1. Users Table (OAuth Authentication)
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    provider VARCHAR(20) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP,
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_provider ON users(provider, provider_user_id);

COMMENT ON TABLE users IS '사용자 계정 정보 (OAuth 소셜 로그인)';
COMMENT ON COLUMN users.user_id IS '사용자 고유 ID (UUID 또는 provider:provider_user_id 형식)';
COMMENT ON COLUMN users.email IS '이메일 주소';
COMMENT ON COLUMN users.name IS '사용자 이름';
COMMENT ON COLUMN users.avatar_url IS '프로필 이미지 URL';
COMMENT ON COLUMN users.provider IS 'OAuth 제공자 (google, kakao, naver)';
COMMENT ON COLUMN users.provider_user_id IS '제공자에서의 사용자 ID';

-- ============================================================
-- 2. Conversations Table
-- ============================================================

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255),
    chat_type VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    turn_count INTEGER DEFAULT 0,
    last_compaction_at INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    CONSTRAINT fk_conversations_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_expires_at ON conversations(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_active ON conversations(is_active, updated_at);

COMMENT ON TABLE conversations IS '대화 세션 정보';
COMMENT ON COLUMN conversations.conversation_id IS '대화 고유 ID';
COMMENT ON COLUMN conversations.session_id IS '프론트엔드 세션 ID (고유)';
COMMENT ON COLUMN conversations.user_id IS '사용자 ID (로그인 사용자만, NULL = 게스트)';
COMMENT ON COLUMN conversations.chat_type IS '채팅 유형 (dispute, general)';
COMMENT ON COLUMN conversations.is_active IS '활성 대화 여부';
COMMENT ON COLUMN conversations.turn_count IS '대화 턴 수';
COMMENT ON COLUMN conversations.last_compaction_at IS '마지막 compaction 턴 번호';
COMMENT ON COLUMN conversations.expires_at IS '만료 시각 (게스트 세션만)';

-- ============================================================
-- 3. Conversation Turns Table
-- ============================================================

CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(conversation_id, turn_number)
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_conversation ON conversation_turns(conversation_id, turn_number);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_created ON conversation_turns(created_at);

COMMENT ON TABLE conversation_turns IS '대화 턴 기록';
COMMENT ON COLUMN conversation_turns.turn_id IS '턴 고유 ID';
COMMENT ON COLUMN conversation_turns.conversation_id IS '대화 ID (FK)';
COMMENT ON COLUMN conversation_turns.turn_number IS '턴 순서 (0부터 시작)';
COMMENT ON COLUMN conversation_turns.role IS '역할 (user, assistant)';
COMMENT ON COLUMN conversation_turns.content IS '메시지 내용';
COMMENT ON COLUMN conversation_turns.metadata IS '메타데이터 (JSONB, 선택사항)';

-- ============================================================
-- 4. Conversation Summaries Table
-- ============================================================

CREATE TABLE IF NOT EXISTS conversation_summaries (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    purchase_item TEXT,
    purchase_date TEXT,
    purchase_amount TEXT,
    purchase_place TEXT,
    dispute_type TEXT,
    dispute_details TEXT,
    desired_resolution TEXT,
    key_facts JSONB,
    compacted_turn_count INTEGER NOT NULL,
    compacted_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_summaries_conversation ON conversation_summaries(conversation_id);

COMMENT ON TABLE conversation_summaries IS '대화 요약 (Compaction)';
COMMENT ON COLUMN conversation_summaries.summary_id IS '요약 고유 ID';
COMMENT ON COLUMN conversation_summaries.conversation_id IS '대화 ID (FK, UNIQUE)';
COMMENT ON COLUMN conversation_summaries.purchase_item IS '구매 품목';
COMMENT ON COLUMN conversation_summaries.purchase_date IS '구매 날짜';
COMMENT ON COLUMN conversation_summaries.purchase_amount IS '구매 금액';
COMMENT ON COLUMN conversation_summaries.purchase_place IS '구매 장소';
COMMENT ON COLUMN conversation_summaries.dispute_type IS '분쟁 유형';
COMMENT ON COLUMN conversation_summaries.dispute_details IS '분쟁 상세 내용';
COMMENT ON COLUMN conversation_summaries.desired_resolution IS '원하는 해결 방법';
COMMENT ON COLUMN conversation_summaries.key_facts IS '주요 사실 정보 (JSONB)';
COMMENT ON COLUMN conversation_summaries.compacted_turn_count IS 'Compaction된 턴 수';

-- ============================================================
-- 5. OAuth Sessions Table
-- ============================================================

CREATE TABLE IF NOT EXISTS oauth_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_sessions_user ON oauth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_sessions_expires ON oauth_sessions(expires_at);

COMMENT ON TABLE oauth_sessions IS 'OAuth 세션 정보 (토큰 저장)';
COMMENT ON COLUMN oauth_sessions.session_id IS '세션 고유 ID';
COMMENT ON COLUMN oauth_sessions.user_id IS '사용자 ID (FK)';
COMMENT ON COLUMN oauth_sessions.provider IS 'OAuth 제공자';
COMMENT ON COLUMN oauth_sessions.access_token IS 'Access Token (암호화 권장)';
COMMENT ON COLUMN oauth_sessions.refresh_token IS 'Refresh Token (암호화 권장)';
COMMENT ON COLUMN oauth_sessions.expires_at IS '토큰 만료 시각';

-- ============================================================
-- 6. Triggers for Updated_at
-- ============================================================

-- Conversations 테이블 updated_at 자동 갱신
CREATE OR REPLACE FUNCTION update_conversations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_conversations_updated_at
BEFORE UPDATE ON conversations
FOR EACH ROW
EXECUTE FUNCTION update_conversations_updated_at();

-- Users 테이블 updated_at 자동 갱신
CREATE OR REPLACE FUNCTION update_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_users_updated_at();

-- ============================================================
-- 7. Data Validation
-- ============================================================

-- Check constraints (idempotent - safe for re-runs)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_chat_type') THEN
        ALTER TABLE conversations ADD CONSTRAINT check_chat_type
            CHECK (chat_type IN ('dispute', 'general'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_role') THEN
        ALTER TABLE conversation_turns ADD CONSTRAINT check_role
            CHECK (role IN ('user', 'assistant', 'system'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_provider') THEN
        ALTER TABLE users ADD CONSTRAINT check_provider
            CHECK (provider IN ('google', 'kakao', 'naver'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_oauth_provider') THEN
        ALTER TABLE oauth_sessions ADD CONSTRAINT check_oauth_provider
            CHECK (provider IN ('google', 'kakao', 'naver'));
    END IF;
END $$;

-- ============================================================
-- 완료
-- ============================================================

-- Verify all tables created
DO $$
BEGIN
    RAISE NOTICE '✓ Migration 004_conversation_memory.sql completed successfully';
    RAISE NOTICE '  - users table created';
    RAISE NOTICE '  - conversations table created';
    RAISE NOTICE '  - conversation_turns table created';
    RAISE NOTICE '  - conversation_summaries table created';
    RAISE NOTICE '  - oauth_sessions table created';
    RAISE NOTICE '';
    RAISE NOTICE '⚠️  Next steps:';
    RAISE NOTICE '   1. Grant permissions if needed: GRANT ALL ON ALL TABLES IN SCHEMA public TO your_user;';
    RAISE NOTICE '   2. Test with: SELECT * FROM users LIMIT 1;';
END $$;
