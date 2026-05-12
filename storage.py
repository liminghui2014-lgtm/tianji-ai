"""
天纪AI 数据存储层
=================
SQLite 单文件，零配置。未来可迁移到 PostgreSQL。
存储: 用户 → 命盘 → 解读 → 对话 → 支付状态
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "tianji.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """建表（幂等）"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            gender TEXT,
            birth_city TEXT,
            birth_lon REAL,
            birth_date_solar TEXT,
            birth_hour INTEGER,
            birth_minute INTEGER,
            true_solar_hour INTEGER,
            true_solar_minute INTEGER,
            zhi_index INTEGER,
            lunar_date TEXT,
            sizhu TEXT,
            wuxing_ju TEXT,
            shengxiao TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            last_read_at TEXT
        );

        CREATE TABLE IF NOT EXISTS charts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            chart_json TEXT NOT NULL,
            geju_json TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            chart_id INTEGER REFERENCES charts(id),
            content TEXT NOT NULL,
            model TEXT,
            tokens_used INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            chart_id INTEGER REFERENCES charts(id),
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            amount REAL,
            pay_type TEXT,  -- 'single' | 'yearly' | 'wechat_group'
            pay_status TEXT DEFAULT 'pending',  -- 'pending' | 'paid' | 'refunded'
            pay_channel TEXT,  -- 'wechat' | 'alipay' | 'manual'
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,  -- 'reading_requested' | 'chat_asked' | 'share_clicked'
            user_id INTEGER REFERENCES users(id),
            metadata TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);
        CREATE INDEX IF NOT EXISTS idx_charts_user ON charts(user_id);
        CREATE INDEX IF NOT EXISTS idx_readings_user ON readings(user_id);
        CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_event ON analytics(event_type);

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            chart_id INTEGER REFERENCES charts(id),
            feedback_useful INTEGER,  -- 1=有用, 0=不太准
            feedback_wtp TEXT,         -- 付费意愿: "19.9"/"29.9"/"49.9"/"no"
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id);
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════
# 用户
# ═══════════════════════════════════════════════════════════════

def save_user(name, gender, birth_city, birth_lon, birth_date_solar,
              birth_hour, birth_minute, true_h, true_m, zhi_idx,
              lunar_date, sizhu, wuxing, shengxiao):
    """保存或更新用户。返回 user_id。"""
    conn = get_db()
    # 检查是否已有相同信息的用户（最近一次解读）
    cur = conn.execute("""
        SELECT id FROM users
        WHERE name=? AND gender=? AND birth_date_solar=?
        ORDER BY created_at DESC LIMIT 1
    """, (name, gender, birth_date_solar))
    row = cur.fetchone()

    if row:
        conn.execute("""
            UPDATE users SET last_read_at=datetime('now','localtime') WHERE id=?
        """, (row["id"],))
        user_id = row["id"]
    else:
        cur = conn.execute("""
            INSERT INTO users (name, gender, birth_city, birth_lon, birth_date_solar,
                              birth_hour, birth_minute, true_solar_hour, true_solar_minute,
                              zhi_index, lunar_date, sizhu, wuxing_ju, shengxiao)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (name, gender, birth_city, birth_lon, birth_date_solar,
              birth_hour, birth_minute, true_h, true_m, zhi_idx,
              lunar_date, sizhu, wuxing, shengxiao))
        user_id = cur.lastrowid

    conn.commit()
    conn.close()
    return user_id


# ═══════════════════════════════════════════════════════════════
# 命盘 + 解读
# ═══════════════════════════════════════════════════════════════

def save_chart_and_reading(user_id, chart_data, geju_list, reading):
    """保存命盘和解读，返回 chart_id"""
    conn = get_db()

    cur = conn.execute("""
        INSERT INTO charts (user_id, chart_json, geju_json) VALUES (?,?,?)
    """, (user_id, json.dumps(chart_data, ensure_ascii=False),
          json.dumps(geju_list, ensure_ascii=False)))
    chart_id = cur.lastrowid

    conn.execute("""
        INSERT INTO readings (user_id, chart_id, content, model)
        VALUES (?,?,?,?)
    """, (user_id, chart_id, reading, "deepseek-v4"))

    conn.commit()
    conn.close()
    return chart_id


# ═══════════════════════════════════════════════════════════════
# 对话
# ═══════════════════════════════════════════════════════════════

def save_chat(user_id, chart_id, question, answer):
    conn = get_db()
    conn.execute("""
        INSERT INTO chats (user_id, chart_id, question, answer) VALUES (?,?,?,?)
    """, (user_id, chart_id, question, answer))
    conn.commit()
    conn.close()


def load_chat_history(user_id, chart_id, limit=20):
    conn = get_db()
    rows = conn.execute("""
        SELECT question, answer FROM chats
        WHERE user_id=? AND chart_id=?
        ORDER BY id DESC LIMIT ?
    """, (user_id, chart_id, limit)).fetchall()
    conn.close()
    return [(r["question"], r["answer"]) for r in reversed(rows)]


# ═══════════════════════════════════════════════════════════════
# 反馈
# ═══════════════════════════════════════════════════════════════

def save_feedback(user_id, chart_id, useful=None, wtp=None):
    conn = get_db()
    conn.execute("""
        INSERT INTO feedback (user_id, chart_id, feedback_useful, feedback_wtp)
        VALUES (?, ?, ?, ?)
    """, (user_id, chart_id, useful, wtp))
    conn.commit()
    conn.close()

def get_feedback_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as n FROM feedback").fetchone()["n"]
    useful_count = conn.execute("SELECT COUNT(*) as n FROM feedback WHERE feedback_useful=1").fetchone()["n"]
    wtp_rows = conn.execute("""
        SELECT feedback_wtp, COUNT(*) as n FROM feedback
        WHERE feedback_wtp IS NOT NULL GROUP BY feedback_wtp ORDER BY n DESC
    """).fetchall()
    conn.close()
    return {"total": total, "useful": useful_count, "wtp": {r["feedback_wtp"]: r["n"] for r in wtp_rows}}


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════

def get_stats():
    conn = get_db()
    stats = {
        "users": conn.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"],
        "charts": conn.execute("SELECT COUNT(*) as n FROM charts").fetchone()["n"],
        "readings": conn.execute("SELECT COUNT(*) as n FROM readings").fetchone()["n"],
        "chats": conn.execute("SELECT COUNT(*) as n FROM chats").fetchone()["n"],
        "today_users": conn.execute(
            "SELECT COUNT(*) as n FROM users WHERE date(created_at)=date('now','localtime')"
        ).fetchone()["n"],
    }
    conn.close()
    return stats


def get_top_geju(limit=10):
    """热门格局排行"""
    conn = get_db()
    rows = conn.execute("""
        SELECT geju_json FROM charts WHERE geju_json IS NOT NULL
    """).fetchall()
    conn.close()

    from collections import Counter
    counter = Counter()
    for r in rows:
        geju = json.loads(r["geju_json"])
        for g in geju:
            counter[g[0]] += 1
    return counter.most_common(limit)


# ═══════════════════════════════════════════════════════════════
# 免费对话配额 (服务端强校验, 防止客户端绕过)
# ═══════════════════════════════════════════════════════════════

FREE_CHAT_LIMIT = 1  # 每人每个命盘免费对话次数

def get_free_chats_used(user_id, chart_id):
    """查询已使用的免费对话次数"""
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) as n FROM chats WHERE user_id=? AND chart_id=?",
        (user_id, chart_id)
    ).fetchone()["n"]
    conn.close()
    return count

def consume_free_chat(user_id, chart_id) -> bool:
    """尝试消耗一次免费对话配额。返回 True 表示允许, False 表示已用完"""
    used = get_free_chats_used(user_id, chart_id)
    return used < FREE_CHAT_LIMIT

def get_remaining_free_chats(user_id, chart_id) -> int:
    """获取剩余免费对话次数"""
    used = get_free_chats_used(user_id, chart_id)
    return max(0, FREE_CHAT_LIMIT - used)


# 初始化
init_db()
