"""
天纪AI 数据存储层 — Supabase PostgreSQL via REST API（零依赖）
"""
import json
import urllib.request
import urllib.error
from datetime import datetime

URL = "https://hzievtwgskweqpdwmrbp.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh6aWV2dHdnc2t3ZXFwZHdtcmJwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg1OTE3MzksImV4cCI6MjA5NDE2NzczOX0.1t_YKm_wlKdfYRUH3bXcYMNuaAws5_L9j9OH5hdvC_Q"


def _req(method, path, body=None):
    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Supabase {method} {path} failed: {e.code} {err_body}")


# ═══════════════════════════════════ 用户 ═══════════════════════════════════

def save_user(name, gender, birth_city, birth_lon, birth_date_solar,
              birth_hour, birth_minute, true_h, true_m, zhi_idx,
              lunar_date, sizhu, wuxing, shengxiao):
    existing = _req("GET", f"/rest/v1/users?select=id&name=eq.{urllib.request.quote(name)}&gender=eq.{urllib.request.quote(gender)}&birth_date_solar=eq.{urllib.request.quote(birth_date_solar)}&order=created_at.desc&limit=1")
    if existing:
        uid = existing[0]["id"]
        _req("PATCH", f"/rest/v1/users?id=eq.{uid}", {
            "birth_city": birth_city, "birth_lon": birth_lon,
            "birth_hour": birth_hour, "birth_minute": birth_minute,
            "true_hour": true_h, "true_minute": true_m, "zhi_idx": zhi_idx,
            "lunar_date": lunar_date, "sizhu": sizhu, "wuxing": wuxing, "shengxiao": shengxiao,
        })
        return uid
    resp = _req("POST", "/rest/v1/users", {
        "name": name, "gender": gender, "birth_city": birth_city, "birth_lon": birth_lon,
        "birth_date_solar": birth_date_solar, "birth_hour": birth_hour, "birth_minute": birth_minute,
        "true_hour": true_h, "true_minute": true_m, "zhi_idx": zhi_idx,
        "lunar_date": lunar_date, "sizhu": sizhu, "wuxing": wuxing, "shengxiao": shengxiao,
    })
    return resp[0]["id"] if resp else None


# ═══════════════════════════════════ 命盘 & 解读 ═══════════════════════════════════

def save_chart_and_reading(user_id, chart_data, geju_list, reading_text):
    geju_json = json.dumps(geju_list, ensure_ascii=False) if geju_list else "[]"
    wuxing = chart_data.get("五行局", "") if isinstance(chart_data, dict) else ""
    chart_json_str = json.dumps(chart_data, ensure_ascii=False) if isinstance(chart_data, dict) else str(chart_data)

    resp = _req("POST", "/rest/v1/charts", {
        "user_id": user_id, "chart_json": chart_json_str,
        "geju_list": geju_json, "wuxing": wuxing,
    })
    cid = resp[0]["id"] if resp else None

    if cid:
        _req("POST", "/rest/v1/readings", {
            "user_id": user_id, "chart_id": cid, "ai_reading": reading_text,
        })
    return cid


# ═══════════════════════════════════ 对话 ═══════════════════════════════════

def save_chat(user_id, chart_id, question, answer):
    _req("POST", "/rest/v1/chats", {
        "user_id": user_id, "chart_id": chart_id,
        "question": question, "answer": answer,
    })


def consume_free_chat(user_id, chart_id):
    path = f"/rest/v1/chats?select=id&user_id=eq.{user_id}&chart_id=eq.{chart_id}"
    data = _req("GET", path)
    return len(data) < 5


def get_remaining_free_chats(user_id, chart_id):
    path = f"/rest/v1/chats?select=id&user_id=eq.{user_id}&chart_id=eq.{chart_id}"
    data = _req("GET", path)
    return max(0, 5 - len(data))


def load_chat_history(user_id, chart_id, limit=20):
    path = f"/rest/v1/chats?select=question,answer&user_id=eq.{user_id}&chart_id=eq.{chart_id}&order=created_at.desc&limit={limit}"
    rows = _req("GET", path)
    return [(r["question"], r["answer"]) for r in reversed(rows)] if rows else []


# ═══════════════════════════════════ 反馈 ═══════════════════════════════════

def save_feedback(user_id, chart_id, useful=None, wtp=None):
    _req("POST", "/rest/v1/feedback", {
        "user_id": user_id, "chart_id": chart_id,
        "feedback_useful": useful, "feedback_wtp": wtp,
    })


def get_feedback_stats():
    total = len(_req("GET", "/rest/v1/feedback?select=id"))
    useful = len(_req("GET", "/rest/v1/feedback?select=id&feedback_useful=eq.1"))
    wtp_rows = _req("GET", "/rest/v1/feedback?select=feedback_wtp&feedback_wtp=not.is.null")
    wtp_counts = {}
    for r in (wtp_rows or []):
        w = r.get("feedback_wtp")
        if w: wtp_counts[w] = wtp_counts.get(w, 0) + 1
    return {"total": total, "useful": useful, "wtp": wtp_counts}


# ═══════════════════════════════════ 统计 ═══════════════════════════════════

def get_stats():
    return {
        "users": len(_req("GET", "/rest/v1/users?select=id")),
        "charts": len(_req("GET", "/rest/v1/charts?select=id")),
        "readings": len(_req("GET", "/rest/v1/readings?select=id")),
        "chats": len(_req("GET", "/rest/v1/chats?select=id")),
        "today_users": 0,
    }
