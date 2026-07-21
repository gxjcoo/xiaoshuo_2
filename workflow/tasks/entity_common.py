"""
实体处理公共工具

- read_full_text: 优先读原始 novel_path，否则拼接章节目录
- atomic_write_json: 原子写 JSON（先写 .tmp 再 rename），避免中断损坏缓存
- CATEGORIES: 六大实体分类
- MAX_ENTITY_LEN: 各分类最大字符长度
"""

import json
import os
import re
import tempfile
from typing import Any, Dict, Iterable, List, Optional


CATEGORIES = ["person", "place", "weapon", "medicine", "skill", "beast"]

# 各分类实体名最大长度（超过视为描述性短语，非实体名）
MAX_ENTITY_LEN = {
    "person": 8,     # 放宽到 8，容纳道号尊号
    "place": 8,
    "weapon": 10,
    "medicine": 8,
    "skill": 10,
    "beast": 8,
}


# ============================================================
# 模式规则过滤（结构模式，非黑名单枚举）
# 换小说不需要改，只要是中文玄幻/仙侠都适用
# ============================================================

# 通用类别词根：单字，表示"某类事物"。
# 如"剑"是所有剑的类别词根。规则：以词根结尾且长度 <= 3 时视为通用词。
# 例：长剑/宝剑/仙剑（含前置形容词，非专有）会被过滤；混沌珠/惊雷剑（专有）不过滤（长度更长）
GENERIC_CATEGORY_ROOTS = (
    # 武器类
    "剑", "刀", "枪", "斧", "锤", "鞭", "戈", "戟", "弓", "箭",
    # 物品类
    "袋", "囊", "盒", "瓶", "壶", "杯", "碗", "钟", "鼓",
    "珠", "环", "镯", "簪", "扇", "伞", "靴", "鞋", "袍", "衣",
    # 载具/建筑
    "船", "车", "桥", "塔", "阁",
    # 术法类
    "法", "术", "诀", "咒", "阵", "印", "符",
    # 妖兽类
    "妖", "怪", "兽", "精", "灵", "仔",
    # 动物类（常见类别字，非专属名）
    "熊", "虎", "狼", "豹", "狐", "蛇", "鸟", "鱼", "虾", "蟹", "龟",
    "龙", "凤", "麒", "鹏", "雕", "鹰", "鹿", "鼠", "猴", "犬", "牛",
    "马", "羊", "猪", "鸡", "鸭", "鹅",
    # 修炼阶段
    "境", "阶", "层", "期",
)

# 通用修饰词（形容词/量词/描述词）：作为前缀出现时，其后接类别词根 → 通用词
GENERIC_MODIFIERS = (
    # 尺寸/程度
    "长", "短", "大", "小", "轻", "重", "厚", "薄", "宽", "窄",
    # 颜色
    "红", "黄", "蓝", "绿", "紫", "青", "白", "黑", "金", "银", "灰",
    # 品质
    "宝", "灵", "仙", "神", "圣", "凡", "俗", "普通",
    # 状态
    "断", "破", "旧", "新", "老", "幼",
    # 形状
    "圆", "方", "尖", "扁",
    # 强度/性质
    "猛", "凶", "毒", "野", "野生", "普通", "特殊", "奇异",
    # 时间
    "初", "中", "后", "末", "前", "早", "晚",
    # 玄幻修炼动词（"炼气/炼神/炼精"里的"炼""气""精""神"通用组合）
    "炼", "气", "精", "神", "虚", "元", "真",
)

# 通用后缀（表示身份/官职/称呼）：以此结尾即剔除
GENERIC_SUFFIXES = (
    "大人", "国师", "县令", "捕头", "掌柜", "斩妖吏",
    "师叔", "师伯", "师尊", "师兄", "师弟", "师姐", "师妹",
    "员外", "千金", "妖道", "长老", "宗主", "首座", "掌门", "掌教",
    "县丞", "主事", "主簿", "侍郎", "尚书", "太守", "将军",
    "武者", "武修", "妖将", "妖王",
    "前辈", "晚辈", "祖师", "老鬼",
)

# 描述性前缀（外观/衣着）：以此开头即剔除
GENERIC_PREFIXES = (
    "黑袍", "白袍", "青袍", "紫袍", "红袍", "黄袍",
    "黑衣", "白衣", "红衣", "金衣", "青衣", "紫衣", "银衣",
    "年轻", "年老", "半袖", "华服", "锦衣",
)

# 通用人称/官职单字后缀（长度 <= 3 的实体，姓+称谓视为通用）
# 例："周小姐" = 姓+小姐 = 通用称呼；"顾青云小姐" 长度 > 3 → 保留
# 中文亲属/尊称是有限闭集，覆盖：辈分/年龄/性别称谓
GENERIC_PERSON_TITLES = (
    # 女性称谓
    "小姐", "姑娘", "夫人", "娘子", "婆娘",
    # 男性称谓
    "公子", "少爷", "先生", "老爷", "郎君",
    # 亲属辈分
    "叔", "伯", "婶", "姨", "舅", "姑", "嫂",
    "爷", "奶", "公", "婆",
    # 排行称呼（数字/老+排行）
    "哥", "姐", "弟", "妹",
    # 尊老称谓
    "翁", "叟", "老",
)


def is_generic_entity(name: str) -> bool:
    """
    判断是否为通用词/描述性短语，命中任意规则返回 True（应剔除）

    规则（纯模式匹配，无枚举名单）：
    1. 含 "的" 或 "之" → 描述性短语
    2. 长度 <= 3 且以通用类别词根结尾 → 通用组合词
       如"长剑""黑袍""小熊""断刀""炼气境""大鱼""猛虎""熊妖"
       注意：这条规则对短词较激进，但专有实体通常 ≥ 4 字（如"混沌珠"3字但"珠"是词根 → 会被误伤）
       所以额外豁免：如果整个前缀不是修饰词/词根本身，视为专有名（如"混沌珠"的"混沌"是专有词）
    3. 单独的类别词根（长度 == 1）→ 通用类别
    4. 以通用后缀结尾（大人/国师 等）→ 官职称呼
    5. 以描述性前缀开头（黑袍/红衣 等）→ 外观描述
    6. 单姓 + 通用称谓（长度 <= 3）→ 通用称呼
    """
    if not name or not isinstance(name, str):
        return True

    # 规则 1：含"的"/"之"的描述性短语
    if "的" in name or "之" in name:
        return True

    # 规则 2：长度 <= 3 且以类别词根结尾 → 通用组合词
    # 前缀必须由修饰词或类别词根组成（否则视为专有实体，如"混沌珠"的"混沌"是专有名）
    if 2 <= len(name) <= 3:
        for root in GENERIC_CATEGORY_ROOTS:
            if name.endswith(root):
                prefix = name[:-len(root)]
                if not prefix:
                    return True
                # 前缀每个字都是修饰词或类别词根 → 通用组合
                if all(ch in GENERIC_MODIFIERS or ch in GENERIC_CATEGORY_ROOTS
                       for ch in prefix):
                    return True

    # 规则 3：单独的类别词根
    if len(name) == 1 and name in GENERIC_CATEGORY_ROOTS:
        return True

    # 规则 4：以通用后缀结尾
    for suffix in GENERIC_SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            return True
    if name in GENERIC_SUFFIXES:
        return True

    # 规则 5：以描述性前缀开头
    for prefix in GENERIC_PREFIXES:
        if name.startswith(prefix):
            return True

    # 规则 6：单姓 + 通用称谓
    if len(name) <= 3:
        for suffix in GENERIC_PERSON_TITLES:
            if name.endswith(suffix):
                return True

    return False


# 分类优先级：跨类去重时保留优先级更高的那一类
# 优先级：person > place > weapon > skill > medicine > beast
# 除非后缀命中强制分类（如"XX剑"强制 weapon），否则先优先级后后缀提示
# 这样人名同时出现在 person+place → 优先人
CROSS_CAT_PRIORITY = {
    "person": 6,
    "place": 5,
    "weapon": 4,
    "skill": 3,
    "medicine": 2,
    "beast": 1,
}

# 后缀提示：出现下列后缀强制归到对应类，覆盖 CROSS_CAT_PRIORITY
CATEGORY_SUFFIX_HINTS = {
    "weapon": ("剑", "刀", "塔", "袋", "鼎", "幡", "环", "扳指", "宝甲", "宝袍", "印", "符",
               "步履靴", "宝塔", "长刀"),
    "place": ("山", "河", "湖", "宗", "阁", "观", "域", "县", "州", "殿", "府",
              "王朝", "山脉", "国"),
    "medicine": ("丹", "散", "膏", "汤", "血", "心", "肉", "参", "灵芝", "何首乌",
                 "陨铁", "精血"),
    "skill": ("术", "法", "诀", "阵", "印", "步", "咒", "神通", "秘卷"),
    "beast": ("龙", "凤", "妖", "兽", "怪", "精", "熊"),
    # person 无强制后缀，作为默认兜底
}


def read_full_text(novel_path: str, chapters_dir: str) -> str:
    """读取全文：优先原始 novel_path，否则拼接章节目录"""
    if novel_path and os.path.exists(novel_path):
        with open(novel_path, "r", encoding="utf-8") as f:
            return f.read()

    if chapters_dir and os.path.exists(chapters_dir):
        texts = []
        for fname in list_chapter_files(chapters_dir):
            fpath = os.path.join(chapters_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                texts.append(f.read())
        return "\n".join(texts)

    return ""


def list_chapter_files(chapters_dir: str) -> List[str]:
    """按章节号自然序返回章节文件名列表"""
    if not os.path.exists(chapters_dir):
        return []
    files = [
        f for f in os.listdir(chapters_dir)
        if f.endswith(".md") and f[0].isdigit()
    ]

    def _key(name: str) -> int:
        m = re.search(r"(\d+)", name)
        return int(m.group(1)) if m else 0

    return sorted(files, key=_key)


def atomic_write_json(path: str, data: Any) -> None:
    """原子写 JSON：写到同目录临时文件后 rename，避免中断损坏"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(
        prefix=".tmp.", suffix=".json", dir=dir_, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def load_json_if_exists(path: str, default: Any = None) -> Any:
    """存在则读取，否则返回 default"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


# 私用区占位符 —— 保证不会出现在中文小说正文里
PLACEHOLDER_HEAD = "\uE000"
PLACEHOLDER_TAIL = "\uE001"


def make_placeholder(idx: int) -> str:
    """生成第 idx 号占位符，形如 \uE000123\uE001"""
    return f"{PLACEHOLDER_HEAD}{idx}{PLACEHOLDER_TAIL}"
