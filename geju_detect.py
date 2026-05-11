"""
紫微斗数格局自动检测
使用 iztro 输出的命盘数据，检测40+种经典格局
"""


def detect_geju(chart_data):
    """
    检测命盘中的所有格局。
    返回: [(格局名, 类型, 简要说明)]
    类型: '命格' | '富贵' | '特殊' | '警示'
    """
    palaces = chart_data.get("命盘", [])
    if not palaces:
        return []

    # 建立宫位索引：{宫名: 宫位数据}
    p = {pal["宫位"]: pal for pal in palaces}

    # 辅助函数
    def stars_of(gong_name):
        """获取某宫的主星列表"""
        info = p.get(gong_name, {})
        stars = info.get("主星", "")
        return [s.strip() for s in stars.split("、") if s.strip() and s.strip() != "无"]

    def all_stars(gong_name):
        """获取某宫所有星（主+辅）"""
        info = p.get(gong_name, {})
        mains = [s.strip() for s in info.get("主星", "").split("、") if s.strip() and s.strip() != "无"]
        minors = [s.strip() for s in info.get("辅星", "").split("、") if s.strip() and s.strip() != "无"]
        return mains + minors

    def has_star(gong_name, star_name):
        return star_name in all_stars(gong_name)

    def has_any(gong_name, star_names):
        for s in star_names:
            if has_star(gong_name, s):
                return True
        return False

    def has_all(gong_name, star_names):
        return all(has_star(gong_name, s) for s in star_names)

    def is_shen(gong_name):
        return p.get(gong_name, {}).get("身宫", False)

    def dizhi_of(gong_name):
        return p.get(gong_name, {}).get("地支", "")

    def all_palace_stars():
        """返回所有宫位的星集合（去重）"""
        result = set()
        for gong in palaces:
            for s in all_stars(gong["宫位"]):
                if s:
                    result.add(s)
        return result

    def surrounding_palaces(gong_name):
        """获取三方四正的宫名列表：本宫+对宫+两个三合宫"""
        palace_order = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"]
        if gong_name not in palace_order:
            return []
        idx = palace_order.index(gong_name)
        return [
            palace_order[idx],                          # 本宫
            palace_order[(idx + 6) % 12],                # 对宫
            palace_order[(idx + 4) % 12],                # 三合1
            palace_order[(idx + 8) % 12],                # 三合2
        ]

    def stars_in_surrounding(gong_name):
        """获取三方四正的所有星"""
        all_s = set()
        orders = [0, 4, 8, 4]  # 本宫, 对宫, 三合...
        palace_order = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"]
        idx = palace_order.index(gong_name)
        for offset in [0, 4, 8]:
            name = palace_order[(idx + offset) % 12]
            for s in all_stars(name):
                all_s.add(s)
        return all_s

    results = []
    ming_stars = stars_of("命宫")
    ming_all = all_stars("命宫")
    all_s = all_palace_stars()

    # ─── 杀破狼系列 ─── 必须在命宫三方四正才成立
    sha_po_lang = {"七杀", "破军", "贪狼"}
    ming_surrounding = stars_in_surrounding("命宫")
    sha_po_lang_in_ming = sha_po_lang & ming_surrounding
    if len(sha_po_lang_in_ming) >= 3:
        results.append(("杀破狼格", "命格", "七杀、破军、贪狼三星全现于命宫三方四正。命主动荡中开创，不喜安逸。若遇吉星(禄存/天魁/天钺)，开创有成；若遇煞星(擎羊/陀罗)，则动荡加剧需防冒险失控。"))
    elif len(sha_po_lang_in_ming) >= 2:
        missing = sha_po_lang - sha_po_lang_in_ming
        results.append((f"半杀破狼（缺{'/'.join(missing)}）", "命格", f"杀破狼缺{'/'.join(missing)}，有开创之心但格局未全。需看大限流年是否能补足缺失之星曜。"))
    # 杀破狼不在命宫而在迁移宫
    if sha_po_lang & set(all_stars("迁移")):
        results.append(("杀破狼在迁移", "命格", "杀破狼星在迁移宫，主外出闯荡、动中求财。在外地/海外发展的动能较强。"))

    # ─── 紫微系列 ───
    if has_star("命宫", "紫微"):
        if has_star("命宫", "天府"):
            results.append(("紫府同宫格", "富贵", "紫微与天府同坐命宫，帝王配库藏，格局宏大，主富贵双全，但易孤高。"))
        elif has_star("命宫", "七杀"):
            results.append(("紫微七杀格", "命格", "紫微与七杀同宫，权威配肃杀，性格果决刚硬，能成大事但人际关系需留意。"))
        elif has_star("命宫", "破军"):
            results.append(("紫微破军格", "命格", "紫微与破军同宫，帝王出征之象。先破后立，适合变革型事业。"))
        elif has_star("命宫", "贪狼"):
            results.append(("紫微贪狼格", "命格", "紫微与贪狼同宫，帝王+桃花。社交手腕极强，但需防沉迷酒色。"))
        elif has_star("命宫", "天相"):
            results.append(("紫微天相格", "命格", "紫微与天相同宫，帝王配宰相。稳重有谋，善于管理。"))
        else:
            results.append(("紫微独坐格", "富贵", "紫微独坐命宫，帝王星不受杂扰，格局清贵，主领导才能。"))

    # ─── 机月同梁 ───
    ji_yue_tong_liang = {"天机", "太阴", "天同", "天梁"}
    jytl_count = len(ji_yue_tong_liang & set(all_s))
    if jytl_count >= 3:
        results.append(("机月同梁格", "富贵", "天机、太阴、天同、天梁四星至少见三。适合文职、策划、公务员、教育等稳定型事业。古人云：机月同梁作吏人。"))

    # ─── 月朗天门 ───
    if has_star("命宫", "太阴") and dizhi_of("命宫") == "亥":
        results.append(("月朗天门格", "富贵", "太阴在亥宫坐命，如皓月当空。主清贵、学识渊博、晚运佳。"))

    # ─── 日照雷门 ───
    if has_star("命宫", "太阳") and dizhi_of("命宫") == "卯":
        results.append(("日照雷门格", "富贵", "太阳在卯宫坐命，旭日东升之象。主光明磊落、早起发达、名声显赫。"))

    # ─── 巨日同宫 ───
    if has_star("命宫", "巨门") and has_star("命宫", "太阳"):
        results.append(("巨日同宫格", "富贵", "巨门与太阳同宫，口才极佳，适合以口生财——律师、讲师、传媒等。"))

    # ─── 廉贞系列 ───
    if has_star("命宫", "廉贞"):
        if has_star("命宫", "七杀"):
            results.append(("廉贞七杀格", "警示", "廉贞与七杀同宫，性格极端、才华横溢但容易走偏锋。成则大器，败则落魄。需修心养性。"))
        elif has_star("命宫", "破军"):
            results.append(("廉贞破军格", "警示", "廉贞与破军同宫，情绪波动大，宜注意冲动决策。"))
        elif has_star("命宫", "贪狼"):
            results.append(("廉贞贪狼格", "警示", "廉贞与贪狼同宫，桃花与才华并存，但需防因色坏财。"))

    # ─── 武曲系列 ───
    if has_star("命宫", "武曲") and has_star("命宫", "天府"):
        results.append(("武府同宫格", "富贵", "武曲与天府同宫，金融天赋极强，适合银行、投资、财会。"))

    # ─── 三奇加会 ───
    hua_set = set()
    for gong in palaces:
        m_str = gong.get("四化", "")
        if m_str:
            for part in m_str.split("、"):
                part = part.strip()
                if part and "化" in part:
                    hua_set.add(part)
    hua_types = set()
    for h in hua_set:
        if "禄" in h: hua_types.add("化禄")
        if "权" in h: hua_types.add("化权")
        if "科" in h: hua_types.add("化科")
    if len(hua_types) >= 3:
        results.append(("三奇加会格", "富贵", "化禄、化权、化科三奇汇聚。主一生有贵人相助，事业有成，名利双收。"))
    elif len(hua_types) >= 2:
        which = "、".join(hua_types)
        results.append((f"双奇格（{which}）", "特殊", f"{which}汇聚命盘，有中等以上的富贵之气。"))

    # ─── 火铃夹命 / 羊陀夹命 ───
    if (has_star("父母", "火星") or has_star("父母", "铃星")) and (has_star("兄弟", "火星") or has_star("兄弟", "铃星")):
        results.append(("火铃夹命格", "警示", "火星与铃星夹命宫，一生多突发性变动，需有应急能力和储备。"))
    if (has_star("父母", "擎羊") or has_star("父母", "陀罗")) and (has_star("兄弟", "擎羊") or has_star("兄弟", "陀罗")):
        results.append(("羊陀夹命格", "警示", "擎羊与陀罗夹命宫，人生阻难较多，需耐心熬过。"))

    # ─── 命无正曜 ───
    if not ming_stars or ming_stars == ["无"]:
        results.append(("命无正曜格", "特殊", "命宫无主星，需借对宫（迁移宫）星曜来看。人生较被动，容易受环境影响。宜借他人之力。"))

    # ─── 身宫定位 ───
    for gong in palaces:
        if gong.get("身宫"):
            shen_name = gong["宫位"]
            results.append((f"身宫在{shen_name}", "特殊", f"身宫落在{shen_name}宫，后天运势重心在{shen_name}相关领域。"))

    # ─── 五行局 + 命宫 ───
    wuxing = chart_data.get("五行局", "")
    if wuxing:
        results.append((f"{wuxing}", "特殊", f"五行局为{wuxing}，影响命格的气质底色。"))

    return results
