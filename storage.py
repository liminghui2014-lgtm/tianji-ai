"""
天纪AI 数据存储层 — Supabase PostgreSQL（持久化）
"""
import json
import hashlib
from datetime import datetime
from supabase import create_client, Client

# Supabase 初始化（延迟到首次调用，避免 import 时 st.secrets 不可用）
_supabase: Client = None


def _db() -> Client:
    global _supabase
    if _supabase is None:
        import streamlit as st
        url = "https://hzievtwgskweqpdwmrbp.supabase.co"
        key = "sb_publishable_6__CyQykjVd_sGlTghec-g_a_8mklZV"
        try:
            url = st.secrets.get("SUPABASE_URL", url)
            key = st.secrets.get("SUPABASE_KEY", key)
        except Exception:
            pass
        _supabase = create_client(url, key)
    return _supabase


# ═══════════════════════════════════ 建表（首次运行手动执行一次） ═══════════════════════════════════

def init_db():
    """在 Supabase SQL Editor 中执行一次即可。这里不做自动建表。"""
    pass  # Supabase 用 SQL Editor 手动建表，或在代码中检测


INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT,
    birth_city TEXT,
    birth_lon REAL,
    birth_date_solar TEXT,
    birth_hour INTEGER,
    birth_minute INTEGER,
    true_hour INTEGER,
    true_minute INTEGER,
    zhi_idx INTEGER,
    lunar_date TEXT,
    sizhu TEXT,
    wuxing TEXT,
    shengxiao TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE TABLE IF NOT EXISTS charts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    chart_json JSONB,
    geju_list JSONB,
    wuxing TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE TABLE IF NOT EXISTS readings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    chart_id INTEGER,
    ai_reading TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE TABLE IF NOT EXISTS chats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    chart_id INTEGER,
    question TEXT,
    answer TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')::text
);

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    chart_id INTEGER,
    feedback_useful INTEGER,
    feedback_wtp TEXT,
    created_at TEXT DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')::text
);
"""


# ═══════════════════════════════════ 用户 ═══════════════════════════════════

def save_user(name, gender, birth_city, birth_lon, birth_date_solar,
              birth_hour, birth_minute, true_h, true_m, zhi_idx,
              lunar_date, sizhu, wuxing, shengxiao):
    db = _db()
    existing = db.table("users").select("id").eq("name", name).eq("gender", gender).eq("birth_date_solar", birth_date_solar).order("created_at", desc=True).limit(1).execute()
    if existing.data:
        uid = existing.data[0]["id"]
        db.table("users").update({
            "birth_city": birth_city, "birth_lon": birth_lon,
            "birth_hour": birth_hour, "birth_minute": birth_minute,
            "true_hour": true_h, "true_minute": true_m, "zhi_idx": zhi_idx,
            "lunar_date": lunar_date, "sizhu": sizhu, "wuxing": wuxing, "shengxiao": shengxiao,
        }).eq("id", uid).execute()
        return uid
    resp = db.table("users").insert({
        "name": name, "gender": gender, "birth_city": birth_city, "birth_lon": birth_lon,
        "birth_date_solar": birth_date_solar, "birth_hour": birth_hour, "birth_minute": birth_minute,
        "true_hour": true_h, "true_minute": true_m, "zhi_idx": zhi_idx,
        "lunar_date": lunar_date, "sizhu": sizhu, "wuxing": wuxing, "shengxiao": shengxiao,
    }).execute()
    return resp.data[0]["id"] if resp.data else None


# ═══════════════════════════════════ 命盘 & 解读 ═══════════════════════════════════

def save_chart_and_reading(user_id, chart_data, geju_list, reading_text):
    db = _db()
    geju_json = json.dumps(geju_list, ensure_ascii=False) if geju_list else "[]"
    wuxing = chart_data.get("五行局", "") if isinstance(chart_data, dict) else ""
    chart_json_str = json.dumps(chart_data, ensure_ascii=False) if isinstance(chart_data, dict) else str(chart_data)

    chart_resp = db.table("charts").insert({
        "user_id": user_id, "chart_json": chart_json_str,
        "geju_list": geju_json, "wuxing": wuxing,
    }).execute()
    cid = chart_resp.data[0]["id"] if chart_resp.data else None

    if cid:
        db.table("readings").insert({
            "user_id": user_id, "chart_id": cid, "ai_reading": reading_text,
        }).execute()
    return cid


# ═══════════════════════════════════ 对话 ═══════════════════════════════════

def save_chat(user_id, chart_id, question, answer):
    _db().table("chats").insert({
        "user_id": user_id, "chart_id": chart_id,
        "question": question, "answer": answer,
    }).execute()


def consume_free_chat(user_id, chart_id):
    db = _db()
    count = db.table("chats").select("id", count="exact").eq("user_id", user_id).eq("chart_id", chart_id).execute()
    return count.count is None or count.count < 5


def get_remaining_free_chats(user_id, chart_id):
    db = _db()
    count = db.table("chats").select("id", count="exact").eq("user_id", user_id).eq("chart_id", chart_id).execute()
    used = count.count or 0
    return max(0, 5 - used)


def load_chat_history(user_id, chart_id, limit=20):
    resp = _db().table("chats").select("question, answer").eq("user_id", user_id).eq("chart_id", chart_id).order("created_at", desc=True).limit(limit).execute()
    if resp.data:
        return [(r["question"], r["answer"]) for r in reversed(resp.data)]
    return []


# ═══════════════════════════════════ 反馈 ═══════════════════════════════════

def save_feedback(user_id, chart_id, useful=None, wtp=None):
    _db().table("feedback").insert({
        "user_id": user_id, "chart_id": chart_id,
        "feedback_useful": useful, "feedback_wtp": wtp,
    }).execute()


def get_feedback_stats():
    db = _db()
    total = db.table("feedback").select("id", count="exact").execute()
    useful = db.table("feedback").select("id", count="exact").eq("feedback_useful", 1).execute()
    wtp_resp = db.table("feedback").select("feedback_wtp").not_.is_("feedback_wtp", "null").execute()
    wtp_counts = {}
    for r in (wtp_resp.data or []):
        w = r.get("feedback_wtp")
        if w: wtp_counts[w] = wtp_counts.get(w, 0) + 1
    return {"total": total.count or 0, "useful": useful.count or 0, "wtp": wtp_counts}


# ═══════════════════════════════════ 统计 ═══════════════════════════════════

def get_stats():
    db = _db()
    return {
        "users": db.table("users").select("id", count="exact").execute().count or 0,
        "charts": db.table("charts").select("id", count="exact").execute().count or 0,
        "readings": db.table("readings").select("id", count="exact").execute().count or 0,
        "chats": db.table("chats").select("id", count="exact").execute().count or 0,
        "today_users": 0,
    }
