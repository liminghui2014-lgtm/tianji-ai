"""
天纪AI - 倪海夏风格紫微斗数解读
================================
iztro排盘 + 真太阳时 + 天纪RAG + DeepSeek解读
"""

import streamlit as st
import json
import subprocess
import os
import hashlib
import random
from pathlib import Path
from datetime import datetime, timedelta
from anthropic import Anthropic
from geju_detect import detect_geju
from storage import save_user, save_chart_and_reading, save_chat, load_chat_history, get_stats

BASE_DIR = Path(__file__).parent
CALCULATOR = BASE_DIR / "chart_calculator.js"

# Streamlit Cloud 自动装 Node.js 依赖
import subprocess as _sp
_node_modules = BASE_DIR / "node_modules" / "iztro"
if not _node_modules.exists():
    _sp.run(["npm", "install"], cwd=str(BASE_DIR), capture_output=True)

# ================================================================
# 配置
# ================================================================

def _load_config():
    try:
        token = st.secrets["ANTHROPIC_AUTH_TOKEN"]
        base = st.secrets.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
        model = st.secrets.get("ANTHROPIC_MODEL", "DeepSeek-V4-pro[1m]")
        return token, base, model
    except Exception:
        pass
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        with open(settings_path) as f:
            s = json.load(f)
        env = s.get("env", {})
        return (
            env.get("ANTHROPIC_AUTH_TOKEN", ""),
            env.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
            env.get("ANTHROPIC_MODEL", "DeepSeek-V4-pro[1m]"),
        )
    return "", "https://api.deepseek.com/anthropic", "DeepSeek-V4-pro[1m]"

API_KEY, API_BASE, API_MODEL = _load_config()

# RAG
from tianji_rag import get_rag
TIANJI_RAG = get_rag()

# ================================================================
# 真太阳时
# ================================================================

SHI_CHEN_NAMES = ["子时","丑时","寅时","卯时","辰时","巳时","午时","未时","申时","酉时","戌时","亥时"]

CITY_LON = {
    "北京":116.4,"上海":121.5,"广州":113.3,"深圳":114.1,"成都":104.1,"重庆":106.5,
    "武汉":114.3,"南京":118.8,"杭州":120.2,"西安":108.9,"天津":117.2,"沈阳":123.4,
    "哈尔滨":126.6,"昆明":102.7,"长沙":113.0,"郑州":113.7,"济南":117.0,"青岛":120.3,
    "大连":121.6,"厦门":118.1,"福州":119.3,"合肥":117.3,"南昌":115.9,"贵阳":106.7,
    "兰州":103.8,"南宁":108.3,"石家庄":114.5,"太原":112.5,"呼和浩特":111.7,
    "乌鲁木齐":87.6,"拉萨":91.1,"西宁":101.8,"银川":106.3,"海口":110.3,
    "香港":114.2,"澳门":113.5,"台北":121.5,"其他":120.0,
}

def calc_true_solar_time(birth_date, birth_hour, birth_minute, longitude):
    import math
    day_of_year = birth_date.timetuple().tm_yday
    B = (360/365)*(day_of_year-81)
    B_rad = math.radians(B)
    eot = 9.87*math.sin(2*B_rad) - 7.53*math.cos(B_rad) - 1.5*math.sin(B_rad)
    lon_offset = (longitude-120)*4
    total_minutes = birth_hour*60 + birth_minute + lon_offset + eot
    total_minutes = total_minutes % (24*60)
    if total_minutes < 0:
        total_minutes += 24*60
    true_hour = int(total_minutes//60)
    true_minute = int(total_minutes%60)
    hour_for_zhi = (true_hour+1)%24
    zhi_index = hour_for_zhi//2
    return true_hour, true_minute, zhi_index

def get_time_display(zhi_index):
    ranges = ["23:00-01:00","01:00-03:00","03:00-05:00","05:00-07:00",
              "07:00-09:00","09:00-11:00","11:00-13:00","13:00-15:00",
              "15:00-17:00","17:00-19:00","19:00-21:00","21:00-23:00"]
    return SHI_CHEN_NAMES[zhi_index] + "(" + ranges[zhi_index] + ")"

# ================================================================
# 排盘
# ================================================================

def calculate_chart(birthday, time_idx, gender):
    cmd = ["node", str(CALCULATOR), birthday, str(time_idx), gender]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise Exception("排盘失败: " + result.stderr)
    return json.loads(result.stdout)

# ================================================================
# AI 解读 - 用 .format() 不用 f-string,避免中文引号冲突
# ================================================================

def build_chart_summary(chart_data, geju_list):
    basic = chart_data.get("基本信息", {})
    palaces = chart_data.get("命盘", [])
    geju_text = "\n".join(["- [" + g[0] + "](" + g[1] + "): " + g[2] for g in geju_list]) if geju_list else "(未检测到特殊格局)"
    palace_text = ""
    for p in palaces:
        extras = "[身宫]" if p.get("身宫") else ""
        palace_text += "- {}({}{}){}: 主星[{}] 辅星[{}]\n".format(
            p["宫位"], p["天干"], p["地支"], extras, p["主星"], p["辅星"])
    return basic, geju_text, palace_text

def generate_reading(chart_data, name, geju_list):
    client = Anthropic(api_key=API_KEY, base_url=API_BASE)
    rag_context = TIANJI_RAG.get_context_for_chart(chart_data, max_tokens=6000)
    basic, geju_text, palace_text = build_chart_summary(chart_data, geju_list)

    prompt = """你是倪海夏天纪派紫微斗数解读师。你的解读像一位有智慧的老朋友——不绕弯子，不说废话，直接告诉你你这个人到底怎么回事。

你的风格：
- 第一个句子就要戳中命主——"你是杀破狼格局，这辈子注定不是安稳命"——这种力度
- 把格局的含义用现代人能秒懂的比喻说出来
- 既说天赋也说坑，让人感觉"卧槽这不就是我吗"
- 最后给的建议要能落地，不是"多行善事"这种正确的废话
- 倪师的医者感——诊断人生，开方子
- 用一两句让人想截图分享的金句收尾

以下是天纪原文资料：

{rag}

## 基本信息
- 性别: {gender}
- 阳历: {solar} 农历: {lunar}
- 四柱: {sizhu}
- 五行局: {wuxing}

## 检测格局
{geju}

## 十二宫
{palace}

请按格式解读。开头第一句话必须包含命主的名字和核心格局，让{name}觉得这就是在说我。""".format(
        rag=rag_context,
        gender=basic.get("性别",""),
        solar=basic.get("阳历",""),
        lunar=basic.get("农历",""),
        sizhu=basic.get("四柱",""),
        wuxing=chart_data.get("五行局",""),
        geju=geju_text,
        palace=palace_text,
        name=name,
    )

    response = client.messages.create(
        model=API_MODEL, max_tokens=4096, temperature=0.8,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            return block.text
    return str(response.content[0])


def generate_chat(chart_data, name, geju_list, user_question, chat_history=""):
    client = Anthropic(api_key=API_KEY, base_url=API_BASE)
    rag_context = TIANJI_RAG.get_context_for_chart(chart_data, max_tokens=8000)
    basic, geju_text, palace_text = build_chart_summary(chart_data, geju_list)

    system_prompt = """你是倪海夏先生本人——天纪紫微斗数的大师。{name}正在和你面对面请教命盘问题。你的回答要让{name}感觉倪师真的看透了我的命盘。

## {name}的完整命盘

性别: {gender}
阳历: {solar}  农历: {lunar}
四柱: {sizhu}  五行局: {wuxing}

### 检测格局
{geju}

### 十二宫全盘
{palace}

## 天纪原文参考（倪海夏原话）
{rag}

## 你的回答准则

1. 深: 不是一两句话，而是从命盘出发做系统性分析。如果问事业，不只说适合创业，而要结合命宫+官禄+财帛+大限分析
2. 准: 紧扣{name}命盘里的具体星曜和宫位。每个判断都要落到具体星曜宫位上
3. 敢: 像倪师一样敢下判断。不模棱两可
4. 活: 用现代人能懂的比喻翻译古典术语
5. 结构: 先给结论，再给论据（从命盘哪颗星哪个宫看出来的），最后给落地建议
6. 不恐吓: 如果看到不好的，用留意、注意、多花时间在这块的方式说，不吓人""".format(
        name=name,
        gender=basic.get("性别",""),
        solar=basic.get("阳历",""),
        lunar=basic.get("农历",""),
        sizhu=basic.get("四柱",""),
        wuxing=chart_data.get("五行局",""),
        geju=geju_text,
        palace=palace_text,
        rag=rag_context,
    )

    user_msg = "之前聊过的内容：\n{history}\n\n---\n{name}现在问: {q}\n\n请倪师基于{name}的完整命盘，做一个深度的、全方位的解读。要具体、要敢说、要让人听完觉得值了。".format(
        history=chat_history, name=name, q=user_question)

    response = client.messages.create(
        model=API_MODEL, max_tokens=4096, temperature=0.85,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            return block.text
    return str(response.content[0])

# ================================================================
# UI
# ================================================================

st.set_page_config(page_title="天纪AI", page_icon="\U0001F52E", layout="centered")

st.markdown("""
<style>
  @media (max-width: 768px) {
    .stApp { padding: 0.5rem !important; }
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.2rem !important; }
    .stForm { padding: 10px !important; }
    .stMarkdown p { font-size: 0.95rem !important; line-height: 1.7 !important; }
  }
  input, select, textarea, button { font-size: 16px !important; }
  .stFormSubmitButton button { font-weight: 600 !important; font-size: 1.1rem !important; }
</style>
""", unsafe_allow_html=True)

for key in ["chart_data","reading","geju_list","name","chat_history",
            "true_h","true_m","zhi_idx","hour","minute","city","lon",
            "user_id","chart_id"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "chat_history" else []

st.title("\U0001F52E 天纪AI")
st.caption("紫微斗数 · 倪海夏天纪体系 · AI解读 · 真太阳时校正")
st.markdown("---")

with st.form("input_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("姓名或昵称", placeholder="请输入你的名字...")
        birthday = st.date_input("出生日期(阳历)", value=datetime(2000,1,1),
                                 min_value=datetime(1900,1,1), max_value=datetime.today())
    with col2:
        tc1, tc2 = st.columns(2)
        with tc1:
            birth_hour = st.selectbox("时", list(range(24)), index=8)
        with tc2:
            birth_minute = st.selectbox("分", list(range(60)), index=0)
        city = st.selectbox("出生城市(真太阳时校正)", list(CITY_LON.keys()), index=0)
    gender = st.radio("性别", ["男","女"], horizontal=True)
    st.caption("真太阳时会根据出生地经度自动校正时辰")
    submitted = st.form_submit_button("\U0001F52E 开始解读", type="primary", use_container_width=True)

st.markdown("---")
st.caption("仅供娱乐 · AI生成内容不构成任何建议 · 天纪体系源自倪海夏先生")

if submitted and name:
    try:
        hour, minute = birth_hour, birth_minute
        lon = CITY_LON[city]
        true_h, true_m, zhi_idx = calc_true_solar_time(birthday, hour, minute, lon)

        with st.spinner("排盘中(含真太阳时校正)..."):
            chart_data = calculate_chart(
                "{}-{}-{}".format(birthday.year, birthday.month, birthday.day),
                zhi_idx, gender)
            geju_list = detect_geju(chart_data)

        with st.spinner("AI解读中(约30秒)..."):
            reading = generate_reading(chart_data, name, geju_list)

        basic = chart_data.get("基本信息", {})
        user_id = save_user(
            name, gender, city, lon,
            "{}-{}-{}".format(birthday.year, birthday.month, birthday.day),
            hour, minute, true_h, true_m, zhi_idx,
            basic.get("农历",""), basic.get("四柱",""),
            chart_data.get("五行局",""), basic.get("生肖",""))
        chart_id = save_chart_and_reading(user_id, chart_data, geju_list, reading)

        st.session_state.chart_data = chart_data
        st.session_state.reading = reading
        st.session_state.geju_list = geju_list
        st.session_state.name = name
        st.session_state.user_id = user_id
        st.session_state.chart_id = chart_id
        st.session_state.chat_history = load_chat_history(user_id, chart_id)
        st.session_state.true_h = true_h
        st.session_state.true_m = true_m
        st.session_state.zhi_idx = zhi_idx
        st.session_state.hour = hour
        st.session_state.minute = minute
        st.session_state.city = city
        st.session_state.lon = lon
        st.rerun()
    except Exception as e:
        st.error("出错了: " + str(e))

if st.session_state.chart_data is not None:
    chart_data = st.session_state.chart_data
    reading = st.session_state.reading
    geju_list = st.session_state.geju_list
    name = st.session_state.name
    true_h = st.session_state.true_h
    true_m = st.session_state.true_m
    zhi_idx = st.session_state.zhi_idx
    hour = st.session_state.hour
    minute = st.session_state.minute
    city = st.session_state.city
    lon = st.session_state.lon

    st.markdown("---")
    st.success(name + " 的命盘解读完成")

    time_display = get_time_display(zhi_idx)
    cols = st.columns(5)
    cols[0].metric("北京时间", "{:02d}:{:02d}".format(hour, minute))
    cols[1].metric("出生城市", city + "(" + str(lon) + "E)")
    cols[2].metric("真太阳时", "{:02d}:{:02d}".format(true_h, true_m))
    cols[3].metric("校正时辰", time_display)
    cols[4].metric("五行局", chart_data.get("五行局",""))

    basic = chart_data.get("基本信息",{})
    st.caption("农历 {} · 四柱 {} · 生肖 {}".format(
        basic.get("农历",""), basic.get("四柱",""), basic.get("生肖","")))

    if geju_list:
        st.markdown("---")
        st.subheader("自动检测格局")
        cols_g = st.columns(min(3, len(geju_list)))
        for i, (name_g, type_g, desc) in enumerate(geju_list):
            emoji = "\U0001F3C6" if type_g=="富贵" else "⚡" if type_g=="命格" else "\U0001F4A1" if type_g=="特殊" else "⚠"
            cols_g[i%3].info("{} {}: {}...".format(emoji, name_g, desc[:80]))

    st.markdown("---")
    st.markdown(reading)

    st.markdown("---")
    st.subheader("和倪师聊聊你的命盘")
    chat_tab1, chat_tab2 = st.tabs(["免费体验", "对话记录"])

    with chat_tab1:
        with st.form("chat_form", clear_on_submit=True):
            user_q = st.text_input("想问倪师什么?", placeholder="比如: 我这个命格适合创业吗?")
            chat_submitted = st.form_submit_button("问倪师")
            if chat_submitted and user_q:
                with st.spinner("倪师思考中..."):
                    history_str = "\n".join(["问: {}\n答: {}".format(q,a) for q,a in st.session_state.chat_history[-5:]])
                    chat_reply = generate_chat(chart_data, name, geju_list, user_q, history_str)
                st.session_state.chat_history.append((user_q, chat_reply))
                save_chat(st.session_state.user_id, st.session_state.chart_id, user_q, chat_reply)
                st.rerun()
        st.caption("付费版支持无限多轮对话")

    with chat_tab2:
        if st.session_state.chat_history:
            for q, a in st.session_state.chat_history:
                st.markdown("**问: {}**".format(q))
                st.markdown("**倪师:** {}".format(a))
                st.markdown("---")
        else:
            st.caption("还没有对话记录")

    share_id = ''.join(random.choices('0123456789abcdef', k=6))
    st.markdown("---")
    st.info("分享码: {}  |  截图分享给朋友,让他们也来测!".format(share_id))

    with st.expander("查看命盘数据"):
        st.json(chart_data)
