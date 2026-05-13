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
from storage import save_user, save_chart_and_reading, save_chat, load_chat_history, get_stats, consume_free_chat, get_remaining_free_chats, save_feedback, get_feedback_stats
try:
    from storage import get_or_create_user, check_daily_quota, consume_daily_chat
except ImportError:
    get_or_create_user = lambda p: None
    check_daily_quota = lambda u: (10, False)
    consume_daily_chat = lambda u: None

BASE_DIR = Path(__file__).parent
CALCULATOR = BASE_DIR / "chart_calculator.js"

# Streamlit Cloud / 本地自动装 Node.js 依赖
import subprocess as _sp
import platform as _plat
_node_modules = BASE_DIR / "node_modules" / "iztro"
if not _node_modules.exists():
    npm_cmd = "npm.cmd" if _plat.system() == "Windows" else "npm"
    _sp.run('"{}" install'.format(npm_cmd), cwd=str(BASE_DIR), capture_output=True, shell=True,
            encoding="utf-8", errors="replace")

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
        with open(settings_path, encoding="utf-8") as f:
            s = json.load(f)
        env = s.get("env", {})
        return (
            env.get("ANTHROPIC_AUTH_TOKEN", ""),
            env.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
            env.get("ANTHROPIC_MODEL", "DeepSeek-V4-pro[1m]"),
        )
    return "", "https://api.deepseek.com/anthropic", "DeepSeek-V4-pro[1m]"

API_KEY, API_BASE, API_MODEL = _load_config()
API_MODEL_FAST = API_MODEL.replace("-pro", "-flash")  # flash 比 pro 快3-5倍

# RAG
from tianji_rag import get_rag
TIANJI_RAG = get_rag()

# ================================================================
# 真太阳时
# ================================================================

SHI_CHEN_NAMES = ["子时","丑时","寅时","卯时","辰时","巳时","午时","未时","申时","酉时","戌时","亥时"]

CITY_LON = {
    # 直辖市
    "北京":116.4,"上海":121.5,"天津":117.2,"重庆":106.5,
    # 广东省
    "广州":113.3,"深圳":114.1,"东莞":113.8,"佛山":113.1,"珠海":113.6,"中山":113.4,
    "惠州":114.4,"汕头":116.7,"江门":113.1,"湛江":110.4,"肇庆":112.5,"茂名":110.9,
    # 浙江省
    "杭州":120.2,"宁波":121.5,"温州":120.7,"嘉兴":120.8,"湖州":120.1,"绍兴":120.6,
    "金华":119.7,"台州":121.4,"舟山":122.2,"丽水":119.9,"衢州":118.9,
    # 江苏省
    "南京":118.8,"苏州":120.6,"无锡":120.3,"常州":120.0,"南通":120.9,"徐州":117.2,
    "扬州":119.4,"镇江":119.4,"泰州":119.9,"淮安":119.0,"连云港":119.2,"盐城":120.2,"宿迁":118.3,
    # 福建省
    "福州":119.3,"厦门":118.1,"泉州":118.6,"漳州":117.7,"莆田":119.0,"龙岩":117.0,"三明":117.6,
    # 四川省
    "成都":104.1,"绵阳":104.7,"宜宾":104.6,"泸州":105.4,"南充":106.1,"达州":107.5,"乐山":103.8,
    # 湖北省
    "武汉":114.3,"宜昌":111.3,"襄阳":112.1,"荆州":112.2,"黄石":115.0,"十堰":110.8,
    # 湖南省
    "长沙":113.0,"株洲":113.1,"湘潭":112.9,"衡阳":112.6,"岳阳":113.1,"常德":111.7,
    # 山东省
    "济南":117.0,"青岛":120.3,"烟台":121.4,"潍坊":119.1,"威海":122.1,"临沂":118.4,"淄博":118.1,
    # 河南省
    "郑州":113.7,"洛阳":112.4,"开封":114.3,"南阳":112.5,"新乡":113.9,"许昌":113.8,
    # 河北省
    "石家庄":114.5,"唐山":118.2,"保定":115.5,"邯郸":114.5,"廊坊":116.7,"秦皇岛":119.6,
    # 辽宁省
    "沈阳":123.4,"大连":121.6,"鞍山":123.0,"抚顺":124.0,"锦州":121.1,"营口":122.2,
    # 其他省份省会及重要城市
    "哈尔滨":126.6,"长春":125.3,"吉林":126.5,
    "西安":108.9,"宝鸡":107.2,"咸阳":108.7,
    "昆明":102.7,"大理":100.2,"丽江":100.2,"曲靖":103.8,"保山":99.2,"普洱":101.0,"临沧":100.1,"玉溪":102.5,"昭通":103.7,"楚雄":101.5,"红河":103.3,"文山":104.2,"西双版纳":100.8,"德宏":98.6,"怒江":98.9,"迪庆":99.7,
    "贵阳":106.7,"遵义":106.9,"六盘水":104.8,"安顺":105.9,"毕节":105.3,"铜仁":109.2,"黔东南":107.9,"黔南":107.5,"黔西南":104.9,
    "合肥":117.3,"芜湖":118.4,"马鞍山":118.5,
    "南昌":115.9,"九江":116.0,"赣州":115.0,
    "兰州":103.8,"天水":105.7,
    "南宁":108.3,"桂林":110.3,"柳州":109.4,
    "太原":112.5,"大同":113.3,
    "呼和浩特":111.7,"包头":109.8,"鄂尔多斯":109.8,
    "乌鲁木齐":87.6,"克拉玛依":84.9,
    "拉萨":91.1,"西宁":101.8,"银川":106.3,"海口":110.3,"三亚":109.5,
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

    # 建立宫位索引
    p_idx = {p["宫位"]: i for i, p in enumerate(palaces)}
    palace_order = ["命宫","兄弟","夫妻","子女","财帛","疾厄","迁移","仆役","官禄","田宅","福德","父母"]

    palace_text_lines = []
    for p in palaces:
        gong = p["宫位"]
        shen = " [身宫]" if p.get("身宫") else ""
        sihua = (" 四化: " + p.get("四化", "")) if p.get("四化", "").strip() else ""

        # 计算三方四正
        if gong in palace_order:
            idx = palace_order.index(gong)
            dui = palace_order[(idx+6)%12]  # 对宫
            he1 = palace_order[(idx+4)%12]  # 三合1
            he2 = palace_order[(idx+8)%12]  # 三合2
            sansi = f" 三方: {dui}+{he1}+{he2}"
        else:
            sansi = ""

        palace_text_lines.append(
            f"- {gong}({p['天干']}{p['地支']}{shen}){sansi}: 主星[{p['主星']}] 辅星[{p['辅星']}]{sihua}"
        )

    palace_text = "\n".join(palace_text_lines)
    return basic, geju_text, palace_text

def build_share_card(chart_data, name, geju_list, share_id, reading_text=""):
    """生成分享卡片HTML — AI解读精华, 截图传播用"""
    # 从解读文本中提取 [命盘速览] 部分
    insights = []
    if reading_text:
        in_speed = False
        for line in reading_text.split("\n"):
            line = line.strip()
            if "命盘速览" in line or "速览" in line:
                in_speed = True
                continue
            if in_speed and line.startswith("-"):
                # 格式: "- 关键字: 一句话洞察"
                parts = line[1:].strip().split(":", 1)
                if len(parts) == 2:
                    insights.append((parts[0].strip(), parts[1].strip()))
                elif len(parts) == 1:
                    insights.append(("", parts[0].strip()))
            elif in_speed and line.startswith("###"):
                break
            elif in_speed and not line.startswith("-") and line:
                # 可能是续行, 追加到最后一个 insight
                if insights:
                    last_k, last_v = insights[-1]
                    insights[-1] = (last_k, last_v + " " + line)

    # 如果没解析出来, 用默认数据
    if not insights:
        ming = next((p for p in chart_data.get("命盘", []) if p["宫位"] == "命宫"), {})
        top_geju = geju_list[0][0] if geju_list else "—"
        insights = [
            ("命宫", f"主星 {ming.get('主星','—')}"),
            ("格局", top_geju),
            ("建议", "详情见完整解读"),
        ]

    basic = chart_data.get("基本信息", {})
    insight_html = ""
    colors = ["#c4a870", "#8ba4b4", "#a08050"]
    for i, (label, text) in enumerate(insights[:3]):
        c = colors[i % len(colors)]
        insight_html += f"""
        <div style="background:rgba(255,255,255,0.03);border-radius:8px;padding:12px;border-left:2px solid {c};">
          <div style="font-size:0.6rem;color:{c};letter-spacing:0.04em;margin-bottom:4px;">{label}</div>
          <div style="font-size:0.82rem;color:#e8e0d4;font-weight:500;line-height:1.4;">{text}</div>
        </div>"""

    return f"""<div style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,rgba(196,168,112,0.08),rgba(196,168,112,0.02));border:1px solid rgba(196,168,112,0.2);border-radius:14px;padding:20px 24px;max-width:100%;margin:0 auto;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
      <div>
        <div style="font-size:1rem;font-weight:600;color:#f0e6d2;">{name} · 命盘速览</div>
        <div style="font-size:0.6rem;color:#6b5f4e;margin-top:2px;">{basic.get('四柱','')} · {chart_data.get('五行局','')}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:0.55rem;color:#6b5f4e;letter-spacing:0.06em;">SHARE</div>
        <div style="font-size:0.85rem;font-weight:600;color:#c4a870;letter-spacing:0.06em;">#{share_id}</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      {insight_html}
    </div>
    <div style="text-align:center;margin-top:12px;font-size:0.55rem;color:#6b5f4e;letter-spacing:0.04em;">天纪 AI · 截图分享给朋友一起探索</div>
  </div>"""

def render_star_chart(chart_data):
    palaces = chart_data.get("命盘", [])
    if not palaces:
        return ""
    order_map = {"命宫":0,"兄弟":1,"夫妻":2,"子女":3,"财帛":4,"疾厄":5,
                 "迁移":6,"仆役":7,"官禄":8,"田宅":9,"福德":10,"父母":11}
    ordered = sorted(palaces, key=lambda p: order_map.get(p["宫位"], 99))
    wuxing = chart_data.get("五行局", "")
    cards = []
    for p in ordered:
        is_ming = p["宫位"] == "命宫"
        shen = "身" if p.get("身宫") else ""
        bg = "#3d2e1a" if is_ming else "#1f1a2e"
        bd = "#c4a870" if is_ming else "#333"
        ms = p["主星"] if p["主星"] and p["主星"] != "无" else "借对宫"
        sihua = p.get("四化", "")
        cards.append(f'<div style="background:{bg};border:1px solid {bd};border-radius:6px;padding:6px 4px;text-align:center;font-size:10px;line-height:1.4;"><b style="color:#c4a870">{p["宫位"]}{shen}</b><br><span style="color:#888;font-size:8px">{p["天干"]}{p["地支"]}</span><br><span style="color:#e8e0d4;font-size:9px">{ms}</span><br><span style="color:#8b7e6a;font-size:7px">{p["辅星"]}</span>' + (f'<br><span style="color:#a08050;font-size:7px">{sihua}</span>' if sihua and sihua.strip() else "") + '</div>')
    return f'<div style="max-width:100%;margin:8px 0;font-family:sans-serif;"><div style="text-align:center;color:#6b5f4e;font-size:10px;margin-bottom:6px;">紫微斗数 · 十二宫 · {wuxing}</div><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;">' + "".join(cards) + '</div></div>'

def generate_reading(chart_data, name, geju_list):
    client = Anthropic(api_key=API_KEY, base_url=API_BASE)
    rag_context = TIANJI_RAG.get_context_for_chart(chart_data, max_tokens=4000)
    basic, geju_text, palace_text = build_chart_summary(chart_data, geju_list)
    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = """当前日期：""" + today + """。你是天纪派紫微斗数解读师，师承倪海夏先生。你说话的方式像一位阅历丰富、看透世事的前辈——不卖关子、不故弄玄虚、不绕弯子。你说的话每一句都要从命盘来，落到命盘去。

## 核心铁律

0. **大限流年数据声明。** 当前系统仅提供本命盘（出厂设置）数据，未计算真实的大限流年底层排盘。当用户问及"明年运势"、"现在走什么运"等时间性问题时，必须明确告诉用户："当前仅基于本命盘进行概率推演，具体流年运势需等系统接入大限流年排盘数据后才能给出确定性判断。"严禁在没有数据的情况下捏造具体年份的运势走向。

1. **盘上有才算数，盘上没有不说。** 每一条判断之前，先引用命盘里哪颗星在哪个宫、哪条四化在引动。不允许脱离命盘进行"可能是"、"大概率是"的推测。

2. **话不说死。** 不能说"你注定xxx"、"你这一生xxx"。说"倾向"、"容易"、"后天重心落在"、"如果大限流年引动则"。紫微不是宿命论——命盘给的是概率和倾向，不是判决书。

3. **三层分开讲。**
   - 先讲本命盘（你的出厂设置、性格底色、天赋与坑）
   - 再讲当前大限（近十年的运势重心在哪个宫位、被什么星引动）
   - 最后点一下当前流年（今年哪个宫在动、四化飞哪里、容易有什么变化）
   不要把三层混在一起讲。

4. **每条结论要有出处。** 比如不能说"适合做文职工作"。要这样说："身宫落在财帛宫，后天人生重心容易集中在资源、收入与价值交换上。财帛宫见天机天梁，偏智力型、规划型的求财方式。官禄宫见天同太阳，适合稳定组织、内容服务、管理支持类工作——所以整体倾向文职策划而非完全无框架的冒险。如果大限进一步引动财帛宫，这种倾向会更明显。"

5. **格局判断要有分寸。** 检测到一个格局，不能只说它是什么。要说明——在三方四正里有没有被强化或被破坏？有没有吉星加持（禄存/天魁/天钺）或煞曜干扰（擎羊/陀罗/火星/铃星）？格局的强弱取决于周边星曜的配合。

6. **口吻。** 平和、有分寸、有温度。像一位你信任的长辈在看你的盘，不吓你、不捧你、不说废话。不要"我告诉你啊"这种语气，不要感叹号轰炸，不要刻意制造"卧槽这就是我"的效果——好解读自己会让人产生这种感觉，不需要你喊出来。

## 倪海夏天纪参考
{rag}

## {name}的命盘

性别: {gender}
阳历: {solar} | 农历: {lunar}
四柱: {sizhu}
五行局: {wuxing}

### 检测到以下格局
{geju}

### 十二宫全盘
{palace}

## 解读格式

请按以下结构输出解读：

### 一、本命盘：你的出厂设置
从命宫开始，逐一分析性格底色、思维模式、情感倾向、事业天赋、财富观念。每个判断必须落到具体星曜和宫位上。重点讲：主星是什么在哪个宫、三方四正看到了什么、有没有煞曜干扰、有没有吉星加持。

### 二、身宫与后天重心
身宫落在哪，后天人生的重心天然偏向哪个领域。

### 三、当前大限与流年
当前的大限在哪个宫位，被什么星引动。今年的流年四化飞到哪里，容易有什么变化。

### 四、给你的建议
基于以上分析，给3-5条能落地的建议。可以分事业、感情、健康几个方面。要具体，不空洞。

### 五、[命盘速览]
在你完成以上四个部分的解读后, 严格在全文末尾追加三行速览。每行格式: `- 关键字: 一句话洞察`。这三行是你对{name}命盘最核心的三条判断——可以是天赋、可以是坑、可以是建议。要精炼、要戳人、要让人想截图。每行不超过20字。""".format(
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
        model=API_MODEL_FAST, max_tokens=4096, temperature=0.3,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            return block.text
    return str(response.content[0])


def generate_chat(chart_data, name, geju_list, user_question, chat_history=""):
    client = Anthropic(api_key=API_KEY, base_url=API_BASE)

    # 上下文压缩: 首轮传完整命盘，后续对话传精简画像
    if not chat_history or len(chat_history) < 200:
        # 首轮: 完整数据
        rag_context = TIANJI_RAG.get_context_for_chart(chart_data, max_tokens=4000)
        basic, geju_text, palace_text = build_chart_summary(chart_data, geju_list)
        context_block = """## {name}的命盘

性别: {gender} | 阳历: {solar} | 农历: {lunar}
四柱: {sizhu} | 五行局: {wuxing}

### 格局
{geju}

### 十二宫全盘
{palace}

### 天纪参考
{rag}""".format(
            name=name, gender=basic.get("性别",""), solar=basic.get("阳历",""),
            lunar=basic.get("农历",""), sizhu=basic.get("四柱",""), wuxing=chart_data.get("五行局",""),
            geju=geju_text, palace=palace_text, rag=rag_context,
        )
    else:
        # 后续轮次: 仅带核心格局+关键星曜的精简画像 + 最近对话
        basic = chart_data.get("基本信息", {})
        geju_names = "、".join([g[0] for g in geju_list]) if geju_list else "无特殊格局"
        # 提取命宫关键星曜
        ming_gong = next((p for p in chart_data.get("命盘",[]) if p["宫位"]=="命宫"), {})
        ming_main = ming_gong.get("主星","无")
        ming_sihua = ming_gong.get("四化","")
        context_block = f"""## {name}的精简命盘画像
性别: {basic.get('性别','')} | 四柱: {basic.get('四柱','')} | 五行局: {chart_data.get('五行局','')}
核心格局: {geju_names}
命宫主星: {ming_main} | 命宫四化: {ming_sihua}
(上述精要信息已足够回答当前问题, 如需查其他宫位请告知)"""

    today = datetime.now().strftime("%Y年%m月%d日")
    system_prompt = """当前日期：""" + today + """。你是天纪派紫微斗数解读师，师承倪海夏先生。{name}正在和你面对面讨论ta的命盘。

护栏铁律：
- 每次回复限200字以内
- 结尾必须抛出一个基于具体星曜/宫位的反问（用？结尾），交出话语权
- 拒答"算命/改运/驱邪/做法"，回应"这是紫微斗数传统文化探讨范畴"
- 不承诺任何超自然效果，不惊吓、不恐吓

{context}

## 你的回答准则

0. **大限流年声明。** 当前系统仅计算本命盘数据。如用户问及具体年份运势，必须声明"当前仅基于本命盘推演，具体流年需等系统接入大限流年排盘数据后才能给出确定性判断"。严禁捏造流年运势。

1. **盘上有才算数。** 每一条判断必须引用具体星曜和宫位。
2. **话不说死。** 说"倾向"、"容易"、"如果大限引动则"。不说"你注定"。
3. **结构清楚。** 先给结论 → 再给依据 → 最后给建议。
4. **不恐吓。** 看到煞曜用"留意"、"需要多花时间"的方式说。
5. **用现代比喻翻译古典术语。** 不哗众取宠。
6. **问答有交互感。** {name}问什么你就针对什么回答，不背命盘。""".format(
        name=name, context=context_block,
    )

    user_msg = "【注意：今年是{today}，不是2024年。回答时必须基于{today}来推算时间。】\n\n之前聊过的内容：\n{history}\n\n---\n{name}现在问: {q}\n\n请倪师基于{name}的完整命盘，做一个深度的、全方位的解读。要具体、要敢说、要让人听完觉得值了。".format(
        today=today, history=chat_history, name=name, q=user_question)

    response = client.messages.create(
        model=API_MODEL_FAST, max_tokens=4096, temperature=0.3,
        thinking={"type": "disabled"},
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

st.set_page_config(
    page_title="天纪AI",
    page_icon="\U0001F52E",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ── 全局样式 ──────────────────────────────────
st.markdown("""
<style>
  /* 背景与字体 */
  .stApp { background: linear-gradient(180deg, #1a1625 0%, #1f1a2e 30%, #1a1625 100%); }
  .stApp > header { background: transparent !important; }
  .stApp > footer { background: transparent !important; }

  /* 全局文字 */
  .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif !important;
    line-height: 1.55 !important;
    font-size: 0.9rem !important;
  }
  .stApp { color: #e8e0d4 !important; }
  .stMarkdown p, .stMarkdown li, .stMarkdown div { color: #e8e0d4 !important; line-height: 1.55 !important; font-size: 0.9rem !important; }
  p, li { line-height: 1.55 !important; color: #e8e0d4 !important; font-size: 0.9rem !important; }

  h1 { color: #f0e6d2 !important; font-weight: 300 !important; letter-spacing: 0.04em !important; line-height: 1.3 !important; font-size: 1.5rem !important; }
  h2 { color: #d4c8b0 !important; font-weight: 400 !important; font-size: 0.95rem !important; line-height: 1.4 !important; }
  h3 { color: #c4a870 !important; font-weight: 400 !important; font-size: 0.8rem !important; letter-spacing: 0.06em !important; }

  /* Cards */
  .card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
  }
  .card h3 { margin-top: 0; color: #c4a870; }

  /* 表单 */
  .stTextInput > div > div > input, .stSelectbox > div > div > select {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #e8e0d4 !important; line-height: 1.4 !important;
  }
  .stDateInput > div > div > input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #e8e0d4 !important; line-height: 1.4 !important;
  }
  .stApp label { line-height: 1.5 !important; }
  .stTextInput input, .stSelectbox select { line-height: 1.4 !important; min-height: 38px !important; }
  .stFormSubmitButton button {
    background: linear-gradient(135deg, #8b6914, #c4a870) !important;
    border: none !important;
    color: #1a1625 !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    border-radius: 10px !important;
    padding: 12px 32px !important;
    font-size: 1rem !important;
    transition: all 0.2s !important;
  }
  .stFormSubmitButton button:hover { transform: translateY(-1px); box-shadow: 0 4px 20px rgba(196,168,112,0.3); }

  /* Metrics */
  [data-testid="stMetric"] { background: rgba(255,255,255,0.04); border-radius: 8px; padding: 8px 12px; }
  [data-testid="stMetric"] label { color: #8b7e6a !important; font-size: 0.7rem !important; letter-spacing: 0.04em; }
  [data-testid="stMetric"] div { color: #d4c8b0 !important; }

  /* Expander */
  .stExpander { border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 12px !important; }
  .stExpander > div { background: transparent !important; }

  /* Tabs */
  .stTabs [role="tab"] { color: #8b7e6a !important; }
  .stTabs [role="tab"][aria-selected="true"] { color: #c4a870 !important; border-bottom-color: #c4a870 !important; }

  /* Divider */
  hr { border-color: rgba(255,255,255,0.08) !important; }

  /* Info/Warning boxes */
  .stAlert { background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,255,255,0.1) !important; border-radius: 10px !important; }
  .stAlert p { color: #d4c8b0 !important; }

  /* Captions */
  .stCaption { color: #6b5f4e !important; }

  /* Chat */
  .stChatMessage { background: transparent !important; }
  .stChatMessage [data-testid="stChatMessageContent"] { color: #e8e0d4 !important; }

  @media (max-width: 768px) {
    .stApp { padding: 0.8rem !important; }
    h1 { font-size: 1.2rem !important; }
    p, li, .stMarkdown p { font-size: 0.82rem !important; }
    .stForm { padding: 10px 0 !important; }
    .stTabs { margin-bottom: 20px !important; }
    .stExpander { margin-top: 20px !important; margin-bottom: 40px !important; }
    .stChatMessage { max-width: 100% !important; }
    iframe { max-width: 100% !important; }
  }
</style>
""", unsafe_allow_html=True)

for key in ["chart_data","reading","geju_list","name","chat_history",
            "true_h","true_m","zhi_idx","hour","minute","city","lon",
            "user_id","chart_id","share_id","phone","logged_in","page"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "chat_history" else []
if st.session_state.page is None: st.session_state.page = "landing"
if "chat_bonus" not in st.session_state: st.session_state.chat_bonus = 0
if "feedback_done" not in st.session_state: st.session_state.feedback_done = False

# ── 分享链接路由：?chart_id=xxx 直接加载已有命盘 ──
qp = st.query_params
cid = qp.get("chart_id")
if cid and st.session_state.chart_data is None:
    try:
        cid_int = int(cid)
        import sqlite3
        conn = sqlite3.connect(str(BASE_DIR / "tianji.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT charts.chart_json, readings.ai_reading, charts.geju_list, users.name
            FROM charts
            JOIN readings ON readings.chart_id = charts.id
            JOIN users ON users.id = charts.user_id
            WHERE charts.id = ?
        """, (cid_int,)).fetchone()
        conn.close()
        if row:
            st.session_state.chart_data = json.loads(row["chart_json"])
            st.session_state.reading = row["ai_reading"]
            st.session_state.geju_list = json.loads(row["geju_list"]) if row["geju_list"] else []
            st.session_state.name = row["name"]
            st.session_state.chart_id = cid_int
            st.session_state.user_id = None
            st.session_state.chat_history = []
    except Exception:
        pass

if st.session_state.page == "landing":
    # ── Landing Page ──
    st.markdown("""
    <div style="text-align:center;padding:40px 0 20px;">
      <h1 style="font-size:1.6rem;margin-bottom:8px;letter-spacing:0.04em;">与先哲对话 —— 天纪 AI</h1>
      <p style="color:#b0a090;font-size:0.9rem;line-height:1.6;max-width:480px;margin:0 auto;">
      这不是一次算命，这是一场基于倪海夏体系与紫微斗数哲学的深度自我勘探。
      </p>
    </div>
    """, unsafe_allow_html=True)
    
    _, cta_col, _ = st.columns([1, 1.2, 1])
    with cta_col:
        if st.button("开启勘探", key="lp_cta", use_container_width=True):
            st.session_state.page = "form"
            st.rerun()
    
    st.markdown("---")
    
    # 品牌愿景
    st.markdown("""
    <div style="
      background: rgba(196,168,112,0.06);
      border: 1px solid rgba(196,168,112,0.12);
      border-radius: 8px;
      padding: 14px 18px;
      margin: 0 0 16px 0;
      font-size: 0.82rem;
      line-height: 1.6;
      text-align:center;
    ">
    我致力于将人类历史上伟大的思想通过 AI 具象化。<br>
    紫微斗数不仅是命理，更是中国古代关于时空、性格与命运的统计学与哲学模型。
    </div>
    """, unsafe_allow_html=True)
    
    # 关于天纪
    st.markdown("""
    <div style="
      background: rgba(196,168,112,0.08);
      border: 1px solid rgba(196,168,112,0.2);
      border-radius: 10px;
      padding: 16px 18px;
      margin: 0 0 16px 0;
      font-size: 0.85rem;
      line-height: 1.6;
    ">
    <strong style="color:#c4a870;">什么是天纪</strong><br><br>
    天纪是倪海夏先生讲授的紫微斗数课程，但它的内容远不止算命。<br><br>
    倪师认为，一个人的命运由三部分组成：<br>
    <strong>三分看盘</strong> —— 紫微斗数命盘是「出厂设置」，显示你的天赋、性格、运势走向<br>
    <strong>三分风水</strong> —— 居住环境、方位格局对人生的影响，阳宅阴宅皆在其中<br>
    <strong>三分易理处事</strong> —— 易经的智慧落到日常：什么时候进、什么时候退、怎么和人相处、怎么面对逆境<br><br>
    所以天纪不只是告诉你「命好不好」——它会教你怎么认识自己，怎么与环境相处，怎么在关键时刻做出对的判断。命盘是起点，不是终点。
    </div>
    """, unsafe_allow_html=True)
    
    # RAG 差异化
    st.markdown("""
    <div style="
      background: rgba(196,168,112,0.06);
      border: 1px solid rgba(196,168,112,0.15);
      border-radius: 10px;
      padding: 14px 18px;
      margin: 0 0 16px 0;
      font-size: 0.82rem;
      line-height: 1.5;
    ">
    <strong style="color:#c4a870;">为什么天纪 AI 与普通 AI 不同</strong><br>
    普通 AI 像一个背过维基百科的学生——紫微斗数的术语它都见过，但容易张冠李戴。天纪 AI 基于 87 万字倪师《天纪》原话语料构建 RAG 知识库，每一次回答都先检索倪师真实说过的内容，再以倪师的思维框架生成解读。你听到的不是 AI 的想象，是倪师本人的原话、分寸和智慧。
    </div>
    """, unsafe_allow_html=True)
    
    # 引导提问方向
    st.markdown("""
    <div style="
      background: rgba(196,168,112,0.04);
      border: 1px solid rgba(196,168,112,0.1);
      border-radius: 10px;
      padding: 14px 18px;
      margin: 0 0 12px 0;
      font-size: 0.85rem;
      line-height: 1.6;
    ">
    <strong style="color:#c4a870;">你可以从这些角度了解自己</strong><br><br>
    不只是「我什么时候发财」——天纪能聊的远比算命多：<br><br>
    <strong>命理</strong> —— 我的命盘格局是什么？杀破狼还是机月同梁？适合创业还是守成？<br>
    <strong>风水</strong> —— 家里哪个方位影响我的运势？办公室怎么布置对自己有利？<br>
    <strong>中医健康</strong> —— 命盘里哪些星曜提示了健康隐患？五行失衡怎么调？<br>
    <strong>易经处事</strong> —— 当下这个困局，易经里哪一卦给我启发？是该进还是该等？<br>
    <strong>人生选择</strong> —— 这段感情要不要继续？这个城市适合我发展吗？<br><br>
    不要只问「我命好不好」——命盘是一个地图，怎么走是你的事。天纪的责任是帮你把地图读懂。
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.page == "landing":
        st.markdown("---")
        st.stop()

# 手机号登录
phone_col, _ = st.columns([1, 2])
with phone_col:
    phone_input = st.text_input("手机号（登录后可保存记录，选填）", placeholder="输入手机号，记录你的命盘历史", key="phone_input")
    if phone_input and len(phone_input) == 11 and phone_input.isdigit():
        try:
            uid = get_or_create_user(phone_input)
            st.session_state.user_id = uid
            st.session_state.phone = phone_input
            st.success("已识别")
        except Exception:
            pass

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
st.caption("AI 生成内容 · 仅供娱乐参考 · 天纪体系源自倪海夏先生")

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
        st.session_state.page = "result"
        st.rerun()
    except Exception as e:
        st.error("出错了: " + str(e))

if st.session_state.page == "form":
    st.stop()

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
    st.markdown(f'<div style="text-align:center;padding:12px 0;"><span style="color:#c4a870;font-size:0.9rem;">{name}</span><span style="color:#8b7e6a;font-size:0.75rem;"> · 命盘解读</span></div>', unsafe_allow_html=True)

    time_display = get_time_display(zhi_idx)
    mt_cols = st.columns(5)
    mt_cols[0].metric("北京时间", "{:02d}:{:02d}".format(hour, minute))
    mt_cols[1].metric("出生城市", city)
    mt_cols[2].metric("真太阳时", "{:02d}:{:02d}".format(true_h, true_m))
    mt_cols[3].metric("校正时辰", time_display)
    mt_cols[4].metric("五行局", chart_data.get("五行局",""))

    basic = chart_data.get("基本信息",{})
    st.caption("农历 {} · 四柱 {} · 生肖 {}".format(
        basic.get("农历",""), basic.get("四柱",""), basic.get("生肖","")))

    if geju_list:
        st.markdown("---")
        st.markdown('<div style="font-size:0.9rem;color:#c4a870;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:12px;">格局检测</div>', unsafe_allow_html=True)
        cols_g = st.columns(min(3, len(geju_list)))
        for i, (name_g, type_g, desc) in enumerate(geju_list):
            if type_g == "富贵":
                accent = "#c4a870"
            elif type_g == "命格":
                accent = "#8ba4b4"
            elif type_g == "警示":
                accent = "#c08070"
            else:
                accent = "#8b9e7a"
            cols_g[i%3].markdown(f"""
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-left:3px solid {accent};border-radius:6px;padding:12px;margin-bottom:8px;">
              <div style="font-weight:600;color:{accent};font-size:0.85rem;margin-bottom:4px;">{name_g}</div>
              <div style="color:#8b7e6a;font-size:0.75rem;line-height:1.5;">{desc[:100]}</div>
            </div>
            """, unsafe_allow_html=True)

    # 星盘
    st.html(render_star_chart(chart_data))

    st.markdown("---")
    st.markdown(reading)

    # ── 分享卡片 ──────────────────────────────
    st.markdown("---")
    if "share_id" not in st.session_state or st.session_state.share_id is None:
        st.session_state.share_id = ''.join(random.choices('0123456789abcdef', k=6))

    # ── 与倪师对话（核心差异化，放在解读后最显眼位置）──
    st.markdown("---")
    st.markdown("""
    <div style="background:rgba(196,168,112,0.1);border:1px solid rgba(196,168,112,0.3);border-radius:12px;padding:20px 24px;margin-bottom:12px;text-align:center;">
      <h3 style="color:#c4a870;margin:0 0 4px;">与倪师对话</h3>
      <p style="color:#e8e0d4;font-size:0.85rem;margin:0;">倪师说：三分看盘，三分风水，三分易理处事。<br>不要只问「命好不好」——聊命理、聊风水、聊中医、聊易经、聊人生进退。<br>命盘是地图，怎么走是你的事。天纪的责任是帮你把地图读懂。</p>
    </div>
    """, unsafe_allow_html=True)

    # 配额：10次/日，会员无限
    if st.session_state.user_id:
        try:
            remaining, is_vip = check_daily_quota(st.session_state.user_id)
        except Exception:
            remaining, is_vip = 10, False
    else:
        remaining, is_vip = 10, False

    chat_tab1, chat_tab2 = st.tabs(["与倪师对话", "对话记录"])

    with chat_tab1:
        if remaining > 0 or is_vip:
            if is_vip:
                st.caption("会员无限对话")
            else:
                st.caption("今日剩余 {} 次免费对话".format(remaining))

            # 快捷问题——直接发送，不用表单
            st.markdown('<p style="font-size:0.8rem;color:#e8e0d4;margin:8px 0 4px;">点击直接发送：</p>', unsafe_allow_html=True)
            quick_qs = [
                "我的命盘格局适合做什么？",
                "家里风水怎么调对我的运势好？",
                "健康上有什么要注意的？中医角度怎么调理？",
                "现在遇到一个两难的决定，易经怎么看？",
                "这段感情/婚姻有什么要注意的？",
                "今年财运怎么样？什么时候有转机？",
            ]
            qrow1 = st.columns(3)
            qrow2 = st.columns(3)
            quick_sent = None
            for i, qq in enumerate(quick_qs[:3]):
                with qrow1[i]:
                    if st.button(qq, key=f"qbtn_{i}", use_container_width=True):
                        quick_sent = qq
            for i, qq in enumerate(quick_qs[3:]):
                with qrow2[i]:
                    if st.button(qq, key=f"qbtn_{i+3}", use_container_width=True):
                        quick_sent = qq

            # 手动输入
            user_q = st.text_input("或直接输入你的问题", placeholder="比如: 我这个命格适合创业吗？", key="chat_input")
            submitted = st.button("发送给倪师", key="chat_submit_btn", use_container_width=True)

            # 处理发送
            final_q = quick_sent or (user_q if submitted else None)
            if final_q:
                if not is_vip and remaining <= 0:
                    st.error("今日免费对话已用完。明天重置，或开通会员无限畅聊。")
                else:
                    with st.spinner("倪师思考中..."):
                        history_str = "\n".join(["问: {}\n答: {}".format(q,a) for q,a in st.session_state.chat_history[-3:]])
                        chat_reply = generate_chat(chart_data, name, geju_list, final_q, history_str)
                    st.session_state.chat_history.append((final_q, chat_reply))
                    save_chat(st.session_state.user_id, st.session_state.chart_id, final_q, chat_reply)
                    if st.session_state.user_id and not is_vip:
                        try: consume_daily_chat(st.session_state.user_id)
                        except: pass
                    st.rerun()

        else:
            if is_vip:
                pass  # 会员永远不触发此分支
            else:
                st.info("今日免费对话已用完。明天重置 10 次，或开通会员无限畅聊。¥19.9/月")

    with chat_tab2:
        if st.session_state.chat_history:
            for q, a in st.session_state.chat_history:
                with st.chat_message("user"): st.write(q)
                with st.chat_message("assistant"): st.write(a)
        else:
            st.caption("还没有对话记录。去上面和倪师聊聊吧。")

    # ── 分享卡片 ──
    st.markdown("---")
    share_html = build_share_card(chart_data, name, geju_list, st.session_state.share_id, reading)
    st.components.v1.html(share_html, height=350, scrolling=True)

    share_url = f"{st.query_params.get('_', '')}?chart_id={st.session_state.chart_id}"
    st.markdown(f'<div style="text-align:center;color:#6b5f4e;font-size:0.7rem;padding:8px;">分享链接：<code>?chart_id={st.session_state.chart_id}</code><br>截图或复制链接发给朋友一起探索</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── 反馈（填完后送3次对话）──
    st.markdown("### 这个解读对你有用吗？")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        if st.button("有用", key="tianji_useful", use_container_width=True):
            if st.session_state.user_id and st.session_state.chart_id:
                save_feedback(st.session_state.user_id, st.session_state.chart_id, useful=1)
            if not st.session_state.feedback_done:
                st.session_state.chat_bonus = 3
                st.session_state.feedback_done = True
            st.success("感谢反馈！已获得 3 次额外免费对话")
    with fc2:
        if st.button("不太准", key="tianji_not_useful", use_container_width=True):
            if st.session_state.user_id and st.session_state.chart_id:
                save_feedback(st.session_state.user_id, st.session_state.chart_id, useful=0)
            if not st.session_state.feedback_done:
                st.session_state.chat_bonus = 3
                st.session_state.feedback_done = True
            st.success("感谢反馈！已获得 3 次额外免费对话")

    st.markdown('<p style="margin-top:16px;font-size:0.85rem;">如果可以无限量与倪师对话 + 解锁大限流年 + 合盘解读，你愿意付多少钱？</p>', unsafe_allow_html=True)
    pcols = st.columns(4)
    for i, price in enumerate(["19.9", "49.9", "99", "不愿意"]):
        with pcols[i]:
            if st.button(price, key=f"tianji_wtp_{i}", use_container_width=True):
                if st.session_state.user_id and st.session_state.chart_id:
                    save_feedback(st.session_state.user_id, st.session_state.chart_id, wtp=price)
                if not st.session_state.feedback_done:
                    st.session_state.chat_bonus = 3
                    st.session_state.feedback_done = True
                st.success("已记录，已获得 3 次额外免费对话")

    with st.expander("查看命盘数据"):
        st.json(chart_data)

# ── 全局合规免责 ──
st.markdown("---")
st.markdown('<p style="color:#5a5040;font-size:0.6rem;text-align:center;line-height:1.5;">服务定位：本系统提供基于倪海夏天纪体系的传统文化对话，并非算命服务。<br>AI 生成内容基于公开语料的 RAG 检索，仅供传统文化学习、研究与哲学探讨参考。<br>命运掌握在自己手中，本平台不承诺任何超自然效果，不提供任何形式的迷信敛财、改运及医疗建议。</p>', unsafe_allow_html=True)
