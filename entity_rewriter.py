"""
实体改写映射 - 同结构改编的核心降重层

设计要点：
1. **项目级全局映射**（runtime/global_entity_map.json）带元数据：
   {"characters": {"原名": {"new": "新名", "first_seen_chapter": 3}}}
   确保同一原名跨章永远映射到同一新名，并可反查来源章节。
2. **章节级缓存**（runtime/chapter-XXXX.entity_map.json）保留扁平映射：
   {"characters": {"原名": "新名"}}，便于人读和排查。
3. **格式互通**：apply_entity_rewrite / detect_original_entity_leaks 同时
   接受扁平格式与带元数据格式，内部统一归一为扁平表。
4. **分段扫描**：长章按段落分块送进 LLM，避免后半实体被截断。
5. **硬清洗**：apply_entity_rewrite 按原名长度降序替换，避免短名子串误吞长名；
   detect_original_entity_leaks 输出残留明细，供审计/修订提示用。
"""

import datetime as _dt
import json
import os
import re
from typing import Dict, List, Optional, Union

from config import RUNTIME_DIR, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api

ENTITY_CACHE_SUFFIX = "entity_map.json"
GLOBAL_ENTITY_MAP_FILE = "global_entity_map.json"
ENTITY_CATEGORIES = ("characters", "places", "events", "objects_animals")

# 常用字黑名单：这些字/词绝不能作为实体名被替换，否则会破坏正常文本
# 单字黑名单覆盖最常见的中文虚词、量词、方位词、身体部位等
_ENTITY_BLACKLIST_SINGLE = frozenset([
    "头", "口", "手", "脚", "眼", "心", "脸", "身", "嘴", "耳", "鼻", "眉", "发",
    "人", "大", "小", "上", "下", "左", "右", "前", "后", "里", "外", "中", "内",
    "天", "地", "山", "水", "风", "火", "石", "木", "草", "花", "树", "云", "雨",
    "金", "银", "铁", "铜", "玉", "珠", "刀", "剑", "门", "路", "桥", "车", "船",
    "家", "房", "屋", "城", "村", "镇", "县", "州", "府", "国", "殿", "楼", "阁",
    "老", "新", "男", "女", "长", "少", "公", "母", "好", "坏", "黑", "白", "红",
    "走", "来", "去", "看", "听", "说", "吃", "喝", "坐", "站", "跑", "飞", "打",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万",
    "你", "我", "他", "她", "它", "谁", "这", "那", "什么", "怎么", "哪",
    "的", "了", "着", "过", "地", "得", "把", "被", "让", "给", "对", "向", "从",
    "和", "与", "及", "或", "但", "而", "就", "也", "都", "还", "又", "再", "才",
    "很", "太", "最", "更", "越", "挺", "真", "假", "会", "能", "要", "想", "该",
    "菜", "酒",
])

# 多字黑名单：常见的短词也不应作为实体名
# 设计原则：只排除真正的通用词，不排除有特定含义的名词
_ENTITY_BLACKLIST_MULTI = frozenset([
    # 代词/指示词
    "这个", "那个", "什么", "怎么", "哪里", "这里", "那里", "自己", "别人",
    "大家", "咱们", "我们", "你们", "他们", "她们", "它们",
    # 量词/数词
    "一个", "两个", "几个", "所有", "每个", "某些",
    # 能愿动词/助动词
    "可以", "应该", "能够", "需要", "必须", "已经", "正在", "将要",
    # 判断词/否定词
    "不是", "没有", "还是", "就是", "只是", "都是", "也是",
    # 连词/关联词
    "因为", "所以", "如果", "虽然", "但是", "不过", "然而", "而且",
    "然后", "接着", "于是", "因此", "所以", "总之",
    # 副词
    "突然", "忽然", "居然", "竟然", "果然", "当然", "自然",
    # 趋向动词
    "起来", "出来", "过来", "回来", "下来", "上来",
    # 抽象名词（非实体）
    "地方", "时候", "东西", "事情", "样子", "名字", "声音",

    # ========== 以下是根据实际映射问题新增的 ==========

    # 常见动词/动作词（不应作为实体名）
    "撞见", "看家", "报仇", "自嘲", "拂袖", "驱邪", "诛杀", "反扑",
    "关押", "清洗", "筛查", "炖汤", "干活", "清点", "悟道", "炼器",
    "送死", "吃人", "事发", "共识", "变故", "斗法", "诛灭", "守家",
    "遭遇", "整饬", "羁押", "清查", "炖煮", "劳作", "盘点", "悟法",
    "锻造", "送命", "辟邪", "协议", "变局", "雪恨", "反噬", "食人",
    "旧案暴露", "拂袖而去", "守候待敌",

    # 境界/修为相关术语（不应作为实体名）
    "炼气", "炼神", "炼精", "聚气", "凝神", "炼体",
    "炼气境", "炼神境", "炼精境", "聚气境", "凝神境", "炼体境",
    "炼气初境", "炼气大成", "炼气巅峰", "炼气圆满", "炼气小成",
    "炼神初境", "炼神大成", "炼神巅峰", "炼神圆满",
    "聚气初境", "聚气大成", "聚气巅峰", "聚气圆满", "聚气小成",
    "凝神初境", "凝神大成", "凝神巅峰", "凝神圆满",
    "炼气境初境", "炼气境大成", "炼气境巅峰", "炼气境圆满", "炼气境小成",
    "炼神境初境", "炼神境大成", "炼神境巅峰", "炼神境圆满",
    "聚气境初境", "聚气境大成", "聚气境巅峰", "聚气境圆满", "聚气境小成",
    "凝神境初境", "凝神境大成", "凝神境巅峰", "凝神境圆满",
    "炼神大成之境", "凝神大成之境",
    "炼神级数", "凝神境界", "凝神级数",

    # 常见物品/器物（太通用，不应替换）
    "头发", "包裹", "饭菜", "牛车", "马车", "酒坛", "酒坛子",
    "盘子", "碗筷", "板砖", "拐杖", "水囊", "银票", "银锭",
    "铜板", "铜钱", "令牌", "纸张", "书信", "笔记",
    "丹药", "灵丹", "法宝", "法器", "秘宝", "宝物",

    # 常见称谓（太通用，会破坏正常文本）
    "少女", "丫鬟", "车夫", "樵夫", "捕头", "公差", "大人", "师姐",
    "师尊", "师父", "和尚", "年轻人", "老夫", "贫道", "老丈", "闺女",
    "少爷", "道士", "青年", "国师", "师叔", "陛下", "工匠", "老爷",
    "弟子", "小子",

    # 常见地点词（太通用）
    "京城", "官道", "山上", "山门", "村落", "家乡", "大门", "后山",
    "衙门", "道观", "宗门",

    # 常见事件/状态词
    "斗法之争", "悬赏", "功绩", "功勋", "修为", "境界", "道行",
    "阴神", "元神", "天地", "大道", "天道", "阵法", "阵势",
    "神通", "法力", "真元", "灵气", "天地灵气",
])

# =================== 实体验证（正向规则） ===================
# 核心思路：不靠黑名单排除，而是靠正向规则判断什么"是"合法实体

# 常见中文姓氏（用于判断是否是人名）
_SURNAMES = frozenset([
    "赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚", "卫",
    "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许", "何", "吕", "施", "张",
    "孔", "曹", "严", "华", "金", "魏", "陶", "姜", "戚", "谢", "邹", "喻",
    "柏", "水", "窦", "章", "云", "苏", "潘", "葛", "奚", "范", "彭", "郎",
    "鲁", "韦", "昌", "马", "苗", "凤", "花", "方", "俞", "任", "袁", "柳",
    "丰", "鲍", "史", "唐", "费", "廉", "岑", "薛", "雷", "贺", "倪", "汤",
    "滕", "殷", "罗", "毕", "郝", "邬", "安", "常", "乐", "于", "时", "傅",
    "皮", "卞", "齐", "康", "伍", "余", "元", "卜", "顾", "孟", "平", "黄",
    "和", "穆", "萧", "尹", "姚", "邵", "湛", "汪", "祁", "毛", "禹", "狄",
    "米", "贝", "明", "臧", "计", "伏", "成", "戴", "谈", "宋", "茅", "庞",
    "熊", "纪", "舒", "屈", "项", "祝", "董", "梁", "杜", "阮", "蓝", "闵",
    "席", "季", "麻", "强", "贾", "路", "娄", "危", "江", "童", "颜", "郭",
    "梅", "盛", "林", "刁", "钟", "徐", "邱", "骆", "高", "夏", "蔡", "田",
    "樊", "胡", "凌", "霍", "虞", "万", "支", "柯", "昝", "管", "卢", "莫",
    "经", "房", "裘", "缪", "干", "解", "应", "宗", "丁", "宣", "贲", "邓",
    "郁", "单", "杭", "洪", "包", "诸", "左", "石", "崔", "吉", "钮", "龚",
    "程", "嵇", "邢", "滑", "裴", "陆", "荣", "翁", "荀", "羊", "於", "惠",
    "甄", "曲", "家", "封", "芮", "羿", "储", "靳", "汲", "邴", "糜", "松",
    "井", "段", "富", "巫", "乌", "焦", "巴", "弓", "牧", "隗", "山", "谷",
    "车", "侯", "宓", "蓬", "全", "郗", "班", "仰", "秋", "仲", "伊", "宫",
    "宁", "仇", "栾", "暴", "甘", "钭", "厉", "戎", "祖", "武", "符", "刘",
    "景", "詹", "束", "龙", "叶", "幸", "司", "韶", "郜", "黎", "蓟", "薄",
    "印", "宿", "白", "怀", "蒲", "邰", "从", "鄂", "索", "咸", "籍", "赖",
    "卓", "蔺", "屠", "蒙", "池", "乔", "阴", "郁", "胥", "能", "苍", "双",
    "闻", "莘", "党", "翟", "谭", "贡", "劳", "逄", "姬", "申", "扶", "堵",
    "冉", "宰", "郦", "雍", "却", "璩", "桑", "桂", "濮", "牛", "寿", "通",
    "边", "扈", "燕", "冀", "郏", "浦", "尚", "农", "温", "别", "庄", "晏",
    "柴", "瞿", "阎", "充", "慕", "连", "茹", "习", "宦", "艾", "鱼", "容",
    "向", "古", "易", "慎", "戈", "廖", "庾", "终", "暨", "居", "衡", "步",
    "都", "耿", "满", "弘", "匡", "国", "文", "寇", "广", "禄", "阙", "东",
    "欧", "殳", "沃", "利", "蔚", "越", "夔", "隆", "师", "巩", "厍", "聂",
    "晁", "勾", "敖", "融", "冷", "訾", "辛", "阚", "那", "简", "饶", "空",
    "曾", "毋", "沙", "乜", "养", "鞠", "须", "丰", "巢", "关", "蒯", "相",
    "查", "后", "荆", "红", "游", "竺", "权", "逯", "盖", "益", "桓", "公",
    "万俟", "司马", "上官", "欧阳", "夏侯", "诸葛", "闻人", "东方", "赫连",
    "皇甫", "尉迟", "公羊", "澹台", "公冶", "宗政", "濮阳", "淳于", "单于",
    "太叔", "申屠", "公孙", "仲孙", "轩辕", "令狐", "钟离", "宇文", "长孙",
    "慕容", "鲜于", "闾丘", "司徒", "司空", "亓官", "司寇", "仉", "督", "子车",
    "颛孙", "端木", "巫马", "公西", "漆雕", "乐正", "壤驷", "公良", "拓跋",
    "夹谷", "宰父", "谷梁", "晋", "楚", "闫", "法", "汝", "鄢", "涂", "钦",
    "岳", "帅", "缑", "亢", "况", "郈", "有", "琴", "商", "牟", "佘", "佴",
    "伯", "赏", "墨", "哈", "谯", "笪", "年", "爱", "阳", "佟",
])

# 人物称谓后缀（有这些后缀的一定是人物）
_CHARACTER_TITLE_SUFFIXES = frozenset([
    "道长", "道人", "真人", "道友", "道兄", "仙子", "仙姑", "仙长",
    "大侠", "女侠", "侠客", "侠士", "前辈", "老前辈",
    "长老", "老祖", "掌门", "宗主", "门主", "教主",
    "师兄", "师姐", "师弟", "师妹", "师父", "师尊", "恩师", "师叔", "师伯",
    "大人", "老爷", "老夫人", "夫人", "公子", "少爷", "小姐", "姑娘",
    "王爷", "皇子", "公主", "太子",
    "员外", "乡绅", "掌柜", "老板", "东家", "老板娘",
    "捕头", "都头", "班头", "总管", "管家",
    "大夫", "郎中", "先生",
    "兄弟", "兄台", "贤弟", "贤妹", "仁兄", "贤侄",
    "老丈", "老者", "老翁", "老婆婆",
    "同志", "老师", "教授", "医生", "律师",
    "妖王", "妖将", "妖道", "妖魔",
    "蛟龙", "玄龟", "巨龟",
])

# 地点后缀（有这些后缀的一定是地点）
_PLACE_SUFFIXES = frozenset([
    "城", "县", "镇", "村", "庄", "寨", "堡", "集",
    "山", "峰", "岭", "崖", "谷", "洞", "岛", "洲",
    "河", "江", "湖", "海", "溪", "泉", "潭", "渊",
    "域", "州", "府", "郡", "国", "境", "疆",
    "观", "寺", "庙", "庵", "祠", "殿", "宫", "阁", "楼", "塔",
    "宗", "门", "派", "教",
    "林", "原", "野", "坡", "岗",
])

# 门派/机构后缀
_SECT_SUFFIXES = frozenset([
    "宗", "门", "派", "教", "帮", "会", "盟",
    "府", "司", "殿", "阁", "堂", "院",
])

# 宝物/法宝名的特征词（有这些前缀/后缀的才是专属宝物）
_TREASURE_MARKERS = frozenset([
    "珠", "鼎", "印", "幡", "旗", "塔", "镜", "钟", "炉", "葫",
    "葫", "瓶", "盘", "轮", "环", "佩", "符", "令", "剑", "刀",
    "锏", "枪", "矛", "戟", "斧", "钺", "钩", "叉",
])


def _is_entity_blacklisted(name: str) -> bool:
    """检查实体名是否在黑名单中（不应被替换的常用字/词）。"""
    name = name.strip()
    if not name:
        return True
    if len(name) == 1 and name in _ENTITY_BLACKLIST_SINGLE:
        return True
    if name in _ENTITY_BLACKLIST_MULTI:
        return True
    return False


def _is_valid_character(name: str) -> bool:
    """判断是否是合法的人物实体名。
    
    合法条件（满足任一）：
    1. 有姓氏开头（2字以上）
    2. 有称谓后缀（道长、真人、员外 等）
    3. 有明确的妖/兽/龙等非人角色标记
    4. 名字长度 >= 3 且包含特定字符组合
    """
    name = name.strip()
    if not name or len(name) < 2:
        return False
    
    # 有姓氏开头
    for surname in _SURNAMES:
        if name.startswith(surname) and len(name) > len(surname):
            return True
    
    # 有称谓后缀（不要求前面必须是姓氏）
    for suffix in _CHARACTER_TITLE_SUFFIXES:
        if name.endswith(suffix):
            return True
    
    # 包含妖/魔/鬼/怪/龙/虎/熊/龟 等非人角色标记
    _beast_markers = "妖魔鬼怪龙虎熊龟凤鹤猿蛇狐狼蛛蝎蛟鳌蟹虾鱼"
    for marker in _beast_markers:
        if marker in name and len(name) >= 2:
            return True
    
    return False


def _is_valid_place(name: str) -> bool:
    """判断是否是合法的地点实体名。
    
    合法条件（满足任一）：
    1. 有地点后缀（城、县、山、河 等）
    2. 有方位/修饰词 + 地点词
    """
    name = name.strip()
    if not name or len(name) < 2:
        return False
    
    # 有地点后缀
    for suffix in _PLACE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return True
    
    # 有"X府"、"X宅"、"X邸"等建筑标记
    _building_markers = ["府", "宅", "邸", "院", "园", "苑", "亭", "台", "榭", "廊"]
    for marker in _building_markers:
        if name.endswith(marker) and len(name) > len(marker):
            return True
    
    return False


def _is_valid_sect(name: str) -> bool:
    """判断是否是合法的门派/机构实体名。"""
    name = name.strip()
    if not name or len(name) < 3:
        return False
    
    for suffix in _SECT_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return True
    
    return False


def _is_valid_treasure(name: str) -> bool:
    """判断是否是合法的法宝/宝物实体名。
    
    合法条件：有专属修饰词（如"混沌珠"、"白虹仙剑"、"天魂珠"）
    而不是通用物品（如"剑"、"刀"、"丹药"、"灵芝"）
    """
    name = name.strip()
    if not name or len(name) < 2:
        return False
    
    # 排除通用药材/食材/材料名（这些不是专属宝物）
    _generic_materials = [
        "灵芝", "人参", "何首乌", "灵草", "仙草", "灵药", "丹药",
        "灵石", "灵矿", "陨铁", "玄铁", "精铁", "寒铁",
        "灵木", "灵花", "灵果", "灵液", "灵水",
        "龙血", "凤羽", "龙鳞", "龙骨", "龙角", "龙心", "蛟珠",
        "独角", "逆鳞", "鳞甲", "精血",
    ]
    for mat in _generic_materials:
        if name.endswith(mat) and len(name) > len(mat):
            # 检查前缀是否只是通用修饰词（万年、千年、百年 等）
            prefix = name[:-len(mat)]
            _generic_time = frozenset(["万年", "千年", "百年", "十年", "百年", "千年"])
            if prefix in _generic_time:
                return False
            # 检查前缀是否只是通用形容词
            _generic_adj = frozenset(["长", "短", "大", "小", "新", "旧", "老", "黑", "白", 
                                      "红", "金", "银", "铁", "铜", "玉", "天外", "上古", "远古"])
            if prefix in _generic_adj:
                return False
    
    # 有宝物特征词后缀
    for marker in _TREASURE_MARKERS:
        if name.endswith(marker) and len(name) > len(marker):
            # 额外检查：不能只是"形容词+宝物词"的通用组合
            prefix = name[:-len(marker)]
            _generic_adj = frozenset(["长", "短", "大", "小", "新", "旧", "老", "黑", "白", "红", "金", "银", "铁", "铜", "玉"])
            if prefix in _generic_adj:
                return False
            return True
    
    # 有"珠"、"鼎"、"印"等字且前面有修饰
    for marker in _TREASURE_MARKERS:
        if marker in name and len(name) >= 3:
            # 排除通用组合
            _generic_combos = ["大还丹", "小还丹", "灵丹", "仙丹", "金丹"]
            if name in _generic_combos:
                return False
            return True
    
    return False


def _is_valid_animal(name: str) -> bool:
    """判断是否是合法的动物/妖兽实体名。
    
    只接受有明确妖兽标记的角色（如 '赤玄蛟龙'、'墨熊'、'噬魂妖蛛'）。
    不通过姓氏判断，避免通用药材（如 '万年灵芝'）被误判为角色。
    """
    name = name.strip()
    if not name or len(name) < 2:
        return False
    
    _beast_markers = "妖魔鬼怪龙虎熊龟凤鹤猿蛇狐狼蛛蝎蛟鳌蟹虾鱼"
    for marker in _beast_markers:
        if marker in name and len(name) >= 2:
            return True
    
    return False


def _is_valid_event(name: str) -> bool:
    """判断是否是合法的事件实体名。
    
    合法条件：是一个有具体名称的事件，不是通用动词/状态。
    通常事件名较长（4字以上），且包含特定结构。
    """
    name = name.strip()
    if not name or len(name) < 3:
        return False
    
    # 事件名通常较长，3字以下的大多是通用词
    if len(name) <= 2:
        return False
    
    # 包含"之"字的通常是事件名（如"山门之变"、"白羊县之祸"）
    if "之" in name:
        return True
    
    # 包含特定事件标记
    _event_markers = ["之变", "之祸", "之乱", "之劫", "之役", "之战", "之约", "之盟",
                      "被盗", "脱困", "陨落", "毙命", "遇害", "被杀", "伏杀",
                      "大阵", "阵法", "秘术", "秘法", "功法", "心法", "法诀",
                      "断流", "截江", "破空", "翻身", "围杀", "围攻", "围剿"]
    for marker in _event_markers:
        if marker in name:
            return True
    
    # 长度 >= 4 且不是通用词的可能是事件
    if len(name) >= 4:
        # 排除明显的通用词
        _generic_events = frozenset(["报仇", "撞见", "自嘲", "拂袖", "诛杀", "反扑",
                                     "关押", "清洗", "筛查", "炖汤", "干活", "清点",
                                     "悟道", "炼器", "送死", "吃人", "事发", "共识",
                                     "变故", "斗法", "诛灭", "守家", "遭遇", "整饬",
                                     "羁押", "清查", "炖煮", "劳作", "盘点", "悟法",
                                     "锻造", "送命", "辟邪", "协议", "变局", "雪恨",
                                     "反噬", "食人"])
        if name in _generic_events:
            return False
        return True
    
    return False


def validate_entity(name: str, category: str) -> bool:
    """正向验证：判断 name 是否是 category 类别下的合法实体。
    
    核心逻辑：不靠黑名单排除，而是靠正向规则判断什么"是"合法实体。
    只有通过验证的实体才会被加入映射表。
    """
    name = name.strip()
    if not name:
        return False
    
    # 黑名单作为最后的安全网（只保留最关键的少量词）
    if _is_entity_blacklisted(name):
        return False
    
    if category == "characters":
        return _is_valid_character(name)
    elif category == "places":
        return _is_valid_place(name)
    elif category == "events":
        return _is_valid_event(name)
    elif category == "objects_animals":
        # objects_animals 包含：法宝、妖兽、门派机构等
        return (_is_valid_treasure(name) or 
                _is_valid_sect(name) or
                _is_valid_animal(name))  # 妖兽/动物角色（有明确标记词）
    
    return False

# 章节级映射值类型：str（扁平格式）
# 全局映射值类型：dict（带元数据）或 str（向后兼容旧格式）
EntityMapFlat = Dict[str, Dict[str, str]]
EntityMapRich = Dict[str, Dict[str, Union[str, dict]]]


# =================== 格式转换 ===================

def _normalize_value(v) -> str:
    """从全局表的条目值中提取 new name（兼容扁平 str 和 rich dict）。"""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("new", ""))
    return ""


def flatten_entity_map(entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> EntityMapFlat:
    """将任意格式映射归一为扁平 {"cat": {"原名": "新名"}}。"""
    if not isinstance(entity_map, dict):
        return _empty_map()
    out: EntityMapFlat = {}
    for cat in ENTITY_CATEGORIES:
        out[cat] = {}
        raw = entity_map.get(cat, {}) or {}
        if not isinstance(raw, dict):
            continue
        for old, v in raw.items():
            new = _normalize_value(v)
            if old and new and old != new:
                out[cat][old] = new
    return out


def _to_rich_entry(new_name: str, chapter_number: int) -> dict:
    return {
        "new": new_name,
        "first_seen_chapter": chapter_number,
    }


# =================== 路径与 IO ===================

def _entity_map_path(chapter_number: int) -> str:
    return os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.{ENTITY_CACHE_SUFFIX}")


def _global_entity_map_path() -> str:
    return os.path.join(RUNTIME_DIR, GLOBAL_ENTITY_MAP_FILE)


def _empty_map() -> EntityMapFlat:
    return {cat: {} for cat in ENTITY_CATEGORIES}


def _ensure_categories(m: dict) -> dict:
    if not isinstance(m, dict):
        return _empty_map()
    for cat in ENTITY_CATEGORIES:
        if not isinstance(m.get(cat), dict):
            m[cat] = {}
    return m


def load_cached_entity_map(chapter_number: int) -> Optional[EntityMapFlat]:
    path = _entity_map_path(chapter_number)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return flatten_entity_map(json.load(f))
    except Exception:
        return None


def save_entity_map(chapter_number: int, entity_map: EntityMapFlat) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(_entity_map_path(chapter_number), "w", encoding="utf-8") as f:
        json.dump(flatten_entity_map(entity_map), f, ensure_ascii=False, indent=2)


def load_global_entity_map() -> EntityMapRich:
    """加载项目级全局实体映射（带元数据格式；兼容读取旧扁平格式）。"""
    path = _global_entity_map_path()
    if not os.path.isfile(path):
        return _empty_map()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = _ensure_categories(json.load(f))
        # 向后兼容：旧扁平格式自动升级为 rich 格式（first_seen_chapter=-1 表示未知）
        for cat in ENTITY_CATEGORIES:
            for old, v in list(raw.get(cat, {}).items()):
                if isinstance(v, str):
                    raw[cat][old] = {"new": v, "first_seen_chapter": -1}
        return raw
    except Exception:
        return _empty_map()


def save_global_entity_map(entity_map: EntityMapRich) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(_global_entity_map_path(), "w", encoding="utf-8") as f:
        json.dump(_ensure_categories(entity_map), f, ensure_ascii=False, indent=2)


def merge_entity_maps(
    base: Union[EntityMapFlat, EntityMapRich],
    incoming: Union[EntityMapFlat, EntityMapRich],
    chapter_number: int = -1,
) -> Union[EntityMapFlat, EntityMapRich]:
    """以 base 为权威：base 中已有的原名保留原映射；incoming 中新增的才合入。
    同时阻止 incoming 中新名与 base 中现有新名冲突（撞名时丢弃 incoming 的该条）。

    chapter_number: 传入时对新合入条目打上 first_seen_chapter 标记（仅当 base
    是 rich 格式时有效）。-1 表示未知。
    """
    base = _ensure_categories(json.loads(json.dumps(base or {})))
    if not isinstance(incoming, dict):
        return base
    # 判断 base 是否 rich 格式（第一个非空值是 dict）
    base_is_rich = False
    for cat in ENTITY_CATEGORIES:
        for v in (base.get(cat, {}) or {}).values():
            base_is_rich = isinstance(v, dict)
            break
        if base_is_rich:
            break
    existing_new_names = set()
    existing_old_names = set()  # 新增：收集所有类别的原名
    for cat in ENTITY_CATEGORIES:
        for old, v in (base.get(cat, {}) or {}).items():
            existing_new_names.add(_normalize_value(v))
            if isinstance(old, str):
                existing_old_names.add(old.strip())
    for cat in ENTITY_CATEGORIES:
        new_pairs = incoming.get(cat, {}) or {}
        if not isinstance(new_pairs, dict):
            continue
        for old, v in new_pairs.items():
            if not isinstance(old, str):
                continue
            new_name = _normalize_value(v)
            old = old.strip()
            new_name = new_name.strip()
            if not old or not new_name or old == new_name:
                continue
            if not validate_entity(old, cat):  # 正向验证：只接受合法实体
                continue
            if old in base[cat]:
                continue
            if old in existing_old_names:  # 新增：检查跨类别原名冲突
                continue
            if new_name in existing_new_names:
                continue
            if base_is_rich:
                # 如果 incoming 本身是 rich 且带 first_seen_chapter 就沿用
                if isinstance(v, dict) and v.get("first_seen_chapter", -1) > 0:
                    base[cat][old] = v
                else:
                    base[cat][old] = _to_rich_entry(new_name, chapter_number)
            else:
                base[cat][old] = new_name
            existing_new_names.add(new_name)
    return base


# =================== 实体扫描 ===================

def _split_into_chunks(text: str, max_chars: int = 4500) -> List[str]:
    """按段落把长文切成不超过 max_chars 的若干块。"""
    if not text:
        return []
    paragraphs = [p for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    buf: List[str] = []
    cur = 0
    for p in paragraphs:
        if cur + len(p) + 1 > max_chars and buf:
            chunks.append("\n".join(buf))
            buf = [p]
            cur = len(p)
        else:
            buf.append(p)
            cur += len(p) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks or [text[:max_chars]]


def _scan_chunk_for_entities(
    chunk: str,
    chapter_number: int,
    existing_map: EntityMapFlat,
    chunk_idx: int,
    chunk_total: int,
) -> EntityMapFlat:
    existing_json = json.dumps(flatten_entity_map(existing_map), ensure_ascii=False)
    prompt = (
        f"请扫描第 {chapter_number} 章参考原文【片段 {chunk_idx}/{chunk_total}】中出现的全部实体名，"
        "为每个**尚未在已有映射中**的实体生成一个风格一致但不同的新名字。\n\n"
        "硬规则：\n"
        "1) **只提取以下类型的实体**（专有名词）：\n"
        "   - 人物/角色：有姓名或明确代号的角色（如 '宝寿道长'、'刘员外'、'赤玄蛟龙'）\n"
        "   - 地名/地点：具体的城、县、山、河、域、国名（如 '金阳县'、'丰源山'、'广山域'）\n"
        "   - 门派/机构：具体的宗门、官府、组织名（如 '九霄仙宗'、'猎妖府'、'白虹观'）\n"
        "   - 建筑/场所：具体的楼阁、府邸、道观名（如 '刘家新宅'、'掌域府邸'）\n"
        "   - 有名号的法宝/特殊物品：有专属名称的物品（如 '混沌珠'、'白虹仙剑'、'天魂珠'）\n"
        "   - 有名号的事件：有专属名称的事件（如 '剑气断流'、'山门之变'）\n\n"
        "2) **以下内容绝对不要提取**（不是实体）：\n"
        "   - 常见动词/动作：撞见、看家、报仇、自嘲、拂袖、驱邪、诛杀、反扑、关押、清洗 等\n"
        "   - 境界/修为术语：炼气境、炼神境、聚气境、凝神境、炼气大成、凝神巅峰 等\n"
        "   - 常见物品（无专属名称）：剑、刀、头发、包裹、饭菜、丹药、令牌 等\n"
        "   - 通用称谓（非特定角色）：少女、丫鬟、车夫、大人、青年、弟子、老夫 等\n"
        "   - 通用地点词：京城、官道、山上、山门、衙门、道观 等\n"
        "   - 抽象概念：修为、道行、阴神、元神、天地、大道、天道、灵气、法力 等\n"
        "   - 状态/情绪：变故、共识、拂袖、自嘲 等\n\n"
        "3) 同类实体保持命名风格一致：角色名用同长度、同姓氏风格替换；地名保持同类型后缀。\n"
        "4) 新名不得与原文任一实体名相同；不得与【已有映射】中任一新名相同。\n"
        "5) 不要编造文中不存在的实体；只输出本片段中真实出现过的原名。\n"
        "6) 主角名必须替换；姓氏与名字若可独立出现请分别列出。\n"
        "7) 通用代称（小道士、那年轻人、他）不算实体，不要列出。\n\n"
        f"【已有映射（请避免冲突，不要为已存在的原名再生成新名）】\n{existing_json}\n\n"
        "输出 JSON（字段必须完整，没有就给空对象）：\n"
        "{\n"
        '  "characters": {"原名": "新名"},\n'
        '  "places": {"原名": "新名"},\n'
        '  "events": {"原名": "新名"},\n'
        '  "objects_animals": {"原名": "新名"}\n'
        "}\n\n"
        f"【参考原文片段】\n{chunk}"
    )
    messages = [
        {"role": "system", "content": "你是小说命名专家，只输出合法 JSON。只提取专有名词（人物名、地名、门派名、建筑名、有专属名的法宝/事件），不要提取动词、境界术语、通用物品、通用称谓。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=2000,
        temperature=0.3,
        response_format={"type": "json_object"},
        task_label=f"第{chapter_number}章实体扫描 {chunk_idx}/{chunk_total}",
    )
    if not raw:
        return _empty_map()
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _empty_map()
        return flatten_entity_map(parsed)
    except Exception:
        return _empty_map()


def extract_entity_map_from_reference(
    reference_text: str,
    chapter_number: int,
    existing_map: Optional[Union[EntityMapFlat, EntityMapRich]] = None,
) -> EntityMapFlat:
    """从参考章扫描实体名，结合 existing_map（通常是全局映射）增量产出本章映射。

    返回的是【本章】扫描出的映射（含已有映射里命中的部分），不会原地修改 existing_map。
    """
    if not reference_text or not reference_text.strip():
        return _empty_map()

    base = flatten_entity_map(existing_map)
    chunks = _split_into_chunks(reference_text, max_chars=4500)
    print(f"  实体扫描：第 {chapter_number} 章共 {len(chunks)} 个片段")

    merged = json.loads(json.dumps(base))
    for idx, chunk in enumerate(chunks, start=1):
        delta = _scan_chunk_for_entities(chunk, chapter_number, merged, idx, len(chunks))
        merged = merge_entity_maps(merged, delta)

    # 只返回参考原文中实际出现过的实体
    result = _empty_map()
    for cat in ENTITY_CATEGORIES:
        for old, new in merged.get(cat, {}).items():
            new_name = _normalize_value(new)
            if old and old in reference_text and old != new_name:
                result[cat][old] = new_name
    return result


# =================== 文本改写 ===================

# 通用称谓后缀集合（不限于特定题材，覆盖常见中文称谓）
# 设计原则：包含 1-3 字的常见称谓后缀，支持古风/现代/武侠/仙侠等多题材
_TITLE_SUFFIXES: List[str] = [
    # 道教/仙侠类
    "道长", "道人", "真人", "道友", "道兄", "仙子", "仙姑", "仙长",
    # 武侠/江湖类
    "大侠", "女侠", "侠客", "侠士", "前辈", "老前辈",
    # 门派/师徒类
    "长老", "老祖", "掌门", "宗主", "门主", "教主", "观主",
    "师兄", "师姐", "师弟", "师妹", "师父", "师尊", "恩师", "师叔", "师伯",
    # 官职/权贵类
    "大人", "老爷", "老夫人", "夫人", "公子", "少爷", "小姐", "姑娘",
    "王爷", "皇子", "公主", "太子",
    # 民间/职业类
    "员外", "乡绅", "掌柜", "老板", "东家", "老板娘",
    "捕头", "都头", "班头", "总管", "管家",
    "大夫", "郎中", "先生",
    # 称呼类
    "兄弟", "兄台", "贤弟", "贤妹", "仁兄", "贤侄",
    "老丈", "老者", "老翁", "老婆婆",
    # 现代类
    "同志", "老师", "教授", "医生", "律师",
]


def _extract_name_parts(name: str) -> tuple:
    """提取角色名的核心部分和称谓后缀。
    
    策略：从后向前匹配已知后缀，返回 (核心, 后缀)。
    如果无法识别后缀，返回 (完整名称, "")。
    
    例如：
        '宝寿道长' → ('宝寿', '道长')
        '青云道人' → ('青云', '道人')
        '郑大人'   → ('郑', '大人')
        '小熊'     → ('小熊', '')
    """
    for suffix in _TITLE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return (name[:-len(suffix)], suffix)
    return (name, "")


def _generate_name_variants(old_name: str, new_name: str) -> Dict[str, str]:
    """为角色名生成称谓后缀变体的替换对（保持后缀一致性）。
    
    核心逻辑：
    1. 提取原名的核心+后缀（如 "宝寿道长" → 核心="宝寿", 后缀="道长"）
    2. 提取新名的核心+后缀（如 "青云道人" → 核心="青云", 后缀="道人"）
    3. 对于每个可能的变体后缀，生成：新核心 + 变体后缀
    
    例如：old='宝寿道长', new='青云道人'
    - 宝寿道人 → 青云道人（保持"道人"后缀）
    - 宝寿真人 → 青云真人（保持"真人"后缀）
    - 宝寿道友 → 青云道友（保持"道友"后缀）
    - 宝寿道兄 → 青云道兄（保持"道兄"后缀）
    """
    variants: Dict[str, str] = {}
    
    # 提取原名的核心和后缀
    old_core, old_suffix = _extract_name_parts(old_name)
    if not old_core:
        return variants
    
    # 提取新名的核心
    new_core, _ = _extract_name_parts(new_name)
    if not new_core:
        new_core = new_name
    
    # 如果原名没有后缀，无法生成变体
    if not old_suffix:
        return variants
    
    # 为所有可能的后缀生成变体（排除原名自身）
    for suffix in _TITLE_SUFFIXES:
        if suffix == old_suffix:
            continue  # 跳过原名自身后缀
        
        variant_old = old_core + suffix
        variant_new = new_core + suffix
        
        # 只有变体与原名不同时才添加
        if variant_old != old_name:
            variants[variant_old] = variant_new
    
    return variants


def _flatten_replacements(entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> Dict[str, str]:
    """从任意格式映射提取扁平替换对（含变体扩展）。"""
    pairs: Dict[str, str] = {}
    if not isinstance(entity_map, dict):
        return pairs
    for cat in ENTITY_CATEGORIES:
        m = entity_map.get(cat, {}) or {}
        if not isinstance(m, dict):
            continue
        for old, v in m.items():
            if not isinstance(old, str):
                continue
            new = _normalize_value(v)
            old = old.strip()
            new = new.strip()
            if not old or not new or old == new:
                continue
            # 正向验证：只接受合法实体（防止通用词被错误替换）
            if not validate_entity(old, cat):
                continue
            pairs[old] = new
            
            # 对 characters 类别生成称谓后缀变体
            if cat == "characters":
                variants = _generate_name_variants(old, new)
                for variant_old, variant_new in variants.items():
                    # 只添加原映射中没有明确覆盖的变体
                    if variant_old not in pairs:
                        pairs[variant_old] = variant_new
    
    return pairs


def apply_entity_rewrite(text: str, entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> str:
    """对文本中已知实体名做全局硬替换。按原名长度降序，避免 '赵无' 先替换吃掉 '赵无恤'。

    算法：先扫描全部匹配（长名优先，跳过已被长名覆盖的位置），
    再一次性替换，彻底杜绝三连卡壳。
    """
    if not text or not entity_map:
        return text
    pairs = _flatten_replacements(entity_map)
    if not pairs:
        return text

    sorted_pairs = sorted(pairs.items(), key=lambda kv: len(kv[0]), reverse=True)

    # 第一步：收集所有匹配位置（长名优先，跳过已占位区域）
    # matches: list of (start, end, replacement_text)
    matches = []
    occupied = set()  # 已被匹配覆盖的字符位置

    for old, new in sorted_pairs:
        if not old or old not in text:
            continue
        idx = 0
        while idx <= len(text) - len(old):
            pos = text.find(old, idx)
            if pos == -1:
                break
            match_end = pos + len(old)
            # 检查是否与已占位区域重叠
            overlap = False
            for p in range(pos, match_end):
                if p in occupied:
                    overlap = True
                    break
            if not overlap:
                # 额外检查：如果替换后会产生重复子串（如 "宝塔"→"玲珑宝塔"
                # 导致 "玲珑宝塔"→"玲珑玲珑宝塔"），则跳过
                if _would_create_stutter(text, pos, match_end, new):
                    idx = pos + 1
                    continue
                matches.append((pos, match_end, new))
                for p in range(pos, match_end):
                    occupied.add(p)
            idx = pos + 1

    if not matches:
        return text

    # 第二步：按位置排序，一次性替换
    matches.sort(key=lambda m: m[0])
    result = []
    last_end = 0
    for start, end, replacement in matches:
        result.append(text[last_end:start])
        result.append(replacement)
        last_end = end
    result.append(text[last_end:])
    return "".join(result)


def _would_create_stutter(text: str, match_start: int, match_end: int, replacement: str) -> bool:
    """检查替换后是否会产生重复子串（三连卡壳）。

    例如：text="玲珑宝塔在空中", match "宝塔" at (2,4), replacement="玲珑宝塔"
    替换后 text[0:2] + replacement = "玲珑" + "玲珑宝塔" = "玲珑玲珑宝塔"
    其中 "玲珑" 重复了两次 → 返回 True
    """
    # 获取匹配前后的上下文
    prefix = text[:match_start]  # 匹配前的文本
    # 替换后的结果 = prefix + replacement + text[match_end:]
    combined = prefix + replacement

    # 检查 replacement 的开头是否与 prefix 的结尾形成重复
    # 例如: prefix="玲珑", replacement="玲珑宝塔" → "玲珑玲珑宝塔"
    # 检查 combined 中是否有连续重复的子串
    for check_len in range(1, min(len(replacement), len(prefix)) + 1):
        suffix = prefix[-check_len:]  # prefix 的最后 check_len 个字符
        rep_start = replacement[:check_len]  # replacement 的前 check_len 个字符
        if suffix == rep_start:
            # 检查这个重复子串是否是同一个实体名的一部分
            # 如果 suffix 是某个实体旧名的一部分，且 rep_start 是对应新名的一部分，则跳过
            return True
    return False


def detect_original_entity_leaks(
    text: str,
    entity_map: Union[EntityMapFlat, EntityMapRich, None],
) -> List[Dict]:
    """检测文本中残留的原实体名（含称谓后缀变体）。
    
    返回 [{entity, category, count, expected}, ...]
    对于 characters 类别，除了检测原名，还检测其称谓后缀变体。
    """
    if not text or not entity_map:
        return []
    leaks: List[Dict] = []
    seen_entities: set = set()  # 避免重复报告
    
    for cat in ENTITY_CATEGORIES:
        for old, v in (entity_map.get(cat, {}) or {}).items():
            if not isinstance(old, str):
                continue
            new = _normalize_value(v)
            if not old or old == new:
                continue
            
            # 检测原名
            count = text.count(old)
            if count > 0 and old not in seen_entities:
                leaks.append({
                    "entity": old,
                    "category": cat,
                    "count": count,
                    "expected": new,
                })
                seen_entities.add(old)
            
            # 对 characters 类别，检测称谓后缀变体
            if cat == "characters":
                old_core, old_suffix = _extract_name_parts(old)
                if old_core and old_suffix:
                    new_core, _ = _extract_name_parts(new)
                    if not new_core:
                        new_core = new
                    
                    for suffix in _TITLE_SUFFIXES:
                        if suffix == old_suffix:
                            continue
                        
                        variant_name = old_core + suffix
                        if variant_name != old and variant_name not in seen_entities:
                            count = text.count(variant_name)
                            if count > 0:
                                expected_variant = new_core + suffix
                                leaks.append({
                                    "entity": variant_name,
                                    "category": cat,
                                    "count": count,
                                    "expected": expected_variant,
                                    "is_variant": True,
                                    "original_entity": old,
                                })
                                seen_entities.add(variant_name)
    
    return leaks


def format_entity_leak_report(leaks: List[Dict]) -> str:
    if not leaks:
        return "无原实体残留"
    lines = [f"检测到 {len(leaks)} 个原实体残留："]
    for leak in leaks:
        variant_info = ""
        if leak.get("is_variant"):
            variant_info = f" [变体，原名: {leak.get('original_entity', '?')}]"
        lines.append(
            f"  - {leak['entity']}（{leak['category']}）残留 {leak['count']} 次，应改为 {leak['expected']}{variant_info}"
        )
    return "\n".join(lines)


def detect_duplicate_text(text: str, min_repeat_length: int = 2, max_repeat_length: int = 10) -> List[Dict]:
    """检测文本中的重复字符或短语（如"乾坤乾坤乾坤"）。
    
    返回重复模式列表：[{"pattern": "乾坤", "count": 3, "position": 10}, ...]
    """
    if not text or len(text) < min_repeat_length * 2:
        return []
    
    duplicates = []
    
    # 检测长度为 min_repeat_length 到 max_repeat_length 的重复模式
    for length in range(min_repeat_length, max_repeat_length + 1):
        i = 0
        while i <= len(text) - length * 2:
            pattern = text[i:i + length]
            # 跳过纯标点或空白
            if not pattern.strip() or all(c in '，。！？、；：""''（）【】《》 \t\n' for c in pattern):
                i += 1
                continue
            
            # 计算连续重复次数
            count = 1
            j = i + length
            while j <= len(text) - length and text[j:j + length] == pattern:
                count += 1
                j += length
            
            # 如果重复2次以上，记录
            if count >= 2:
                duplicates.append({
                    "pattern": pattern,
                    "count": count,
                    "position": i,
                    "full_match": pattern * count,
                })
                i = j  # 跳过已检测的重复
            else:
                i += 1
    
    # 合并重叠的检测结果（优先保留更长的模式）
    if not duplicates:
        return []
    
    # 按位置排序
    duplicates.sort(key=lambda x: x["position"])
    
    # 去重：如果两个模式有重叠，保留更长的
    merged = []
    for dup in duplicates:
        if not merged:
            merged.append(dup)
        else:
            last = merged[-1]
            # 检查是否重叠
            if dup["position"] < last["position"] + len(last["full_match"]):
                # 重叠，保留更长的
                if len(dup["full_match"]) > len(last["full_match"]):
                    merged[-1] = dup
            else:
                merged.append(dup)
    
    return merged


def fix_duplicate_text(text: str) -> str:
    """修复文本中的重复字符或短语（如"同门同门同门" → "同门"）。
    
    使用正则匹配 (X){2,} 模式来捕获任意重复2次及以上的词组。
    同时处理尾部单字重复（如"悬赏金金" → "悬赏金"）。
    """
    if not text:
        return text
    
    import re
    
    # 2字词重复2+次的正则修复
    word_repeat_fixes = [
        (r'(同门){2,}', '同门'),
        (r'(神异){2,}', '神异'),
        (r'(龙之){2,}', '龙之'),
        (r'(之争){2,}', '之争'),
        (r'(天地){2,}', '天地'),
        (r'(乾坤){2,}', '天地'),
        (r'(精华){2,}', '精华'),
        (r'(黑衣){2,}', '黑衣'),
        (r'(白衣){2,}', '白衣'),
        (r'(青锋){2,}', '青锋'),
        (r'(灵气){2,}', '灵气'),
        (r'(剑气){2,}', '剑气'),
        (r'(道法){2,}', '道法'),
        (r'(夜夜){2,}', '夜夜'),
    ]
    
    # 尾部单字重复修复（如 悬赏金金 → 悬赏金）
    tail_repeat_fixes = [
        (r'悬赏金金+', '悬赏金'),
        (r'龙心丹丹+', '龙心丹'),
    ]
    
    # 含重复的复合词修复
    compound_fixes = [
        (r'龙血精华精华+', '龙血精华'),
        (r'地地+基石', '地基石'),
        (r'天地天地灵气', '天地灵气'),
    ]
    
    result = text
    
    # 合并所有正则修复，按优先级执行
    all_fixes = compound_fixes + word_repeat_fixes + tail_repeat_fixes
    
    for pattern, replacement in all_fixes:
        # 多次替换以处理嵌套情况
        for _ in range(5):
            new_result = re.sub(pattern, replacement, result)
            if new_result == result:
                break
            result = new_result
    
    return result


def remove_revision_notes(text: str) -> str:
    """移除文本中的修订说明（AI生成时可能留下的编辑痕迹）。
    
    支持的修订说明格式：
    1. 括号内的修订说明：（修订说明：...）或 (修订说明：...)
    2. 章节末尾的修订说明块：以"---"开头，包含"修订说明"的块
    3. 以"修订说明"、"修订记录"、"修改说明"等开头的段落
    """
    if not text:
        return text
    
    import re
    
    result = text
    
    # 1. 移除括号内的修订说明
    # 匹配中文括号或英文括号内的修订说明
    result = re.sub(r'[（(]修订说明[：:][^）)]*[）)]', '', result)
    result = re.sub(r'[（(]修改说明[：:][^）)]*[）)]', '', result)
    result = re.sub(r'[（(]修正说明[：:][^）)]*[）)]', '', result)
    result = re.sub(r'[（(]修订记录[：:][^）)]*[）)]', '', result)
    
    # 2. 移除章节末尾的修订说明块
    # 匹配以"---"开头，包含"修订说明"的块（直到文件末尾）
    revision_block_pattern = r'\n---\s*\n\*\*修订说明\*\*.*$'
    result = re.sub(revision_block_pattern, '', result, flags=re.DOTALL)
    
    # 匹配以"---"开头，包含"修订说明"的块（不带加粗）
    revision_block_pattern2 = r'\n---\s*\n修订说明.*$'
    result = re.sub(revision_block_pattern2, '', result, flags=re.DOTALL)
    
    # 3. 移除以"修订说明"、"修订记录"、"修改说明"等开头的段落
    # 匹配独立的修订说明段落（以换行开头，包含修订说明关键词）
    revision_paragraph_patterns = [
        r'\n修订说明[：:].*?(?=\n\n|\n#|\n\*\*|\Z)',
        r'\n修订记录[：:].*?(?=\n\n|\n#|\n\*\*|\Z)',
        r'\n修改说明[：:].*?(?=\n\n|\n#|\n\*\*|\Z)',
        r'\n修正说明[：:].*?(?=\n\n|\n#|\n\*\*|\Z)',
    ]
    
    for pattern in revision_paragraph_patterns:
        result = re.sub(pattern, '', result, flags=re.DOTALL)
    
    # 清理多余的空行（连续3个以上空行合并为2个）
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result


def fix_sanchi_qingfeng_compound(text: str) -> str:
    """修复实体替换导致的"三尺青锋"错误复合词问题。
    
    当实体替换将"剑"替换为"三尺青锋"后，复合词如"剑身"会变成"三尺青锋身"。
    本函数将这些错误复合词修复为正确的形式，同时保留独立的"三尺青锋"。
    """
    if not text:
        return text
    
    if '三尺青锋' not in text:
        return text
    
    # 优先级从高到低替换（先匹配更长的模式）
    replacements = [
        # 多字组合模式（必须先处理）
        ('青锋灵三尺青锋', '青锋灵剑'),
        ('青锋三尺青锋柄', '青锋剑柄'),
        # "X三尺青锋"模式（X+剑的组合）
        ('玄三尺青锋', '玄剑'),
        ('道三尺青锋', '道剑'),
        ('灵三尺青锋', '灵剑'),
        ('一三尺青锋', '一剑'),
        # "三尺青锋X"模式（剑+X的组合）
        ('三尺青锋身', '剑身'),
        ('三尺青锋光', '剑光'),
        ('三尺青锋鸣', '剑鸣'),
        ('三尺青锋意', '剑意'),
        ('三尺青锋鞘', '剑鞘'),
        ('三尺青锋脊', '剑脊'),
        ('三尺青锋罡', '剑罡'),
        ('三尺青锋芒', '剑芒'),
        ('三尺青锋气', '剑气'),
        ('三尺青锋诀', '剑诀'),
        ('三尺青锋法', '剑法'),
        ('三尺青锋术', '剑术'),
        ('三尺青锋道', '剑道'),
        ('三尺青锋客', '剑客'),
        ('三尺青锋修', '剑修'),
        ('三尺青锋灵', '剑灵'),
        ('三尺青锋阵', '剑阵'),
        ('三尺青锋招', '剑招'),
        ('三尺青锋式', '剑式'),
        ('三尺青锋势', '剑势'),
        ('三尺青锋力', '剑力'),
        ('三尺青锋速', '剑速'),
        ('三尺青锋锋', '剑锋'),
        ('三尺青锋刃', '剑刃'),
        ('三尺青锋柄', '剑柄'),
        ('三尺青锋尖', '剑尖'),
        ('拔三尺青锋', '拔剑'),
        ('断三尺青锋', '断剑'),
        ('铸三尺青锋', '铸剑'),
        ('佩三尺青锋', '佩剑'),
        # 新增模式：复合词和短语
        ('三尺青锋拔弩张', '剑拔弩张'),
        ('白虹三尺青锋', '白虹剑'),
        ('三尺青锋花', '剑花'),
        ('三尺青锋分江河', '剑分江河'),
        ('三尺青锋器有灵', '剑器有灵'),
        ('三尺青锋归鞘', '剑归鞘'),
        ('三尺青锋回鞘', '剑回鞘'),
        ('三尺青锋出鞘', '剑出鞘'),
        ('三尺青锋入鞘', '剑入鞘'),
        ('三尺青锋在鞘中', '剑在鞘中'),
        ('三尺青锋的锋芒', '剑的锋芒'),
        ('三尺青锋的虚影', '剑的虚影'),
        ('三尺青锋的瞬间', '剑的瞬间'),
        ('三尺青锋中', '剑中'),
        ('三尺青锋三尺青锋', '三尺青锋'),  # 重复修正
    ]
    
    result = text
    for old, new in replacements:
        result = result.replace(old, new)
    
    return result


def format_entity_map_for_prompt(entity_map: Union[EntityMapFlat, EntityMapRich, None], max_per_category: int = 0) -> str:
    """把实体映射格式化成提示词块。max_per_category=0 表示不截断（默认列全部）。"""
    if not entity_map:
        return ""
    flat = flatten_entity_map(entity_map)
    label = {
        "characters": "角色名",
        "places": "地名",
        "events": "事件名",
        "objects_animals": "物件/动物名",
    }
    sections: List[str] = []
    for cat in ENTITY_CATEGORIES:
        pairs = flat.get(cat, {}) or {}
        if not pairs:
            continue
        items = list(pairs.items())
        if max_per_category and max_per_category > 0:
            items = items[:max_per_category]
        rendered = "、".join(f"{old}→{new}" for old, new in items)
        sections.append(f"- {label.get(cat, cat)}：{rendered}")
    return "\n".join(sections)


# =================== 预览与反查 ===================

def format_global_map_for_preview(global_map: Union[EntityMapFlat, EntityMapRich, None]) -> str:
    """格式化全局映射表，按类别和来源章节排列，供终端预览。"""
    if not global_map:
        return "（全局实体映射为空）"
    label = {
        "characters": "角色",
        "places": "地名",
        "events": "事件",
        "objects_animals": "物件/动物",
    }
    lines: List[str] = ["=== 全局实体映射 ==="]
    total = 0
    for cat in ENTITY_CATEGORIES:
        entries = (global_map.get(cat, {}) or {})
        if not entries:
            continue
        lines.append(f"\n[{label.get(cat, cat)}] ({len(entries)} 条)")
        for old, v in entries.items():
            if isinstance(v, dict):
                new = v.get("new", "?")
                ch = v.get("first_seen_chapter", "?")
                lines.append(f"  {old} → {new}  (首见: 第{ch}章)")
            else:
                lines.append(f"  {old} → {v}  (首见: 未知)")
            total += 1
    lines.append(f"\n共 {total} 条映射")
    return "\n".join(lines)
