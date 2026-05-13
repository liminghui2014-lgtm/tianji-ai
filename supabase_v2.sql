-- 天纪 V2.0 数据库升级
-- 在 Supabase SQL Editor 中执行

-- 1. users 表（用户系统）
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone text UNIQUE,
    is_vip boolean DEFAULT false,
    vip_expires_at timestamptz,
    daily_chat_count int DEFAULT 0,
    last_active_date date DEFAULT CURRENT_DATE,
    memory_tags jsonb DEFAULT '[]',
    created_at timestamptz DEFAULT now()
);

-- 2. 重构 feedback 表
DROP TABLE IF EXISTS feedback CASCADE;
CREATE TABLE feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    chart_id uuid NOT NULL REFERENCES charts(id),
    rating_score int2 NOT NULL CHECK (rating_score BETWEEN 1 AND 5),
    feedback_tags jsonb DEFAULT '[]',
    text_content text,
    reward_claimed boolean DEFAULT false,
    created_at timestamptz DEFAULT now()
);
-- 防刷：同一用户同一命盘只有一条反馈
CREATE UNIQUE INDEX idx_feedback_user_chart ON feedback(user_id, chart_id);

-- 3. charts 表加 user_id 外键（如果还没有）
-- ALTER TABLE charts ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id);

-- 4. 为现有 charts/readings 数据创建临时 user（如果 users 表为空）
-- INSERT INTO users (id, phone) VALUES (gen_random_uuid(), 'legacy') ON CONFLICT DO NOTHING;
