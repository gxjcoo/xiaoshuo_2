import os

def _load_local_dotenv():
    """从项目根目录 .env 读取环境变量（不覆盖系统已存在变量）。"""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # .env 读取失败时不阻断主流程
        pass

_load_local_dotenv()

# --- API 和路径配置 ---
# 可选: "deepseek" | "doubao"
# 优先使用环境变量覆盖，便于在不同机器/环境切换
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()

if LLM_PROVIDER == "doubao":
    # 豆包（火山方舟 Ark）配置
    API_KEY = os.environ.get("DOUBAO_API_KEY", os.environ.get("ARK_API_KEY", ""))
    BASE_URL = os.environ.get("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    DEFAULT_LLM_MODEL = os.environ.get("DOUBAO_MODEL", "doubao-seed-2-0-pro-260215")
else:
    # DeepSeek 配置
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", os.environ.get("API_KEY", ""))
    BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEFAULT_LLM_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# HTTP 超时（秒）。未设置时 httpx 可能长时间无响应，看起来像「卡住」。
# 生成长章节若超时，可调大环境变量 API_HTTP_READ_TIMEOUT，或在 config 里改默认值。
API_HTTP_CONNECT_TIMEOUT = float(os.environ.get("API_HTTP_CONNECT_TIMEOUT", "30"))
API_HTTP_READ_TIMEOUT = float(os.environ.get("API_HTTP_READ_TIMEOUT", "300"))

# 文件路径
CONTEXT_FILE = 'story_context.json'
PRUNED_ARCHIVE_FILE = 'pruned_context_archive.json'
DEFAULT_INPUT_DIR = 'input_chapters'  # 默认参考章目录（用户自备 numbered .md）
DEFAULT_OUTPUT_DIR = 'output_chapters'  # 默认生成输出目录

# DDD：静态领域目录（相对项目工作目录）
STORY_DOMAIN_DIR = 'story_domain'
RUNTIME_DIR = 'runtime'
AUTHOR_INTENT_FILE = 'author_intent.md'
CURRENT_FOCUS_FILE = 'current_focus.md'
AUDIT_RULES_FILE = 'audit_rules.json'
# 注入提示词时的长度上限（字符），避免超出模型上下文
MAX_DOMAIN_PROMPT_CHARS = 8000
MAX_AUTHOR_INTENT_CHARS = 3000
MAX_CURRENT_FOCUS_CHARS = 2000
# 严格结构适配（STRICT_SOURCE_PLOT）时进一步压缩，减轻「说明书」式上下文抬高 AI 率
MAX_DOMAIN_STRICT_CHARS = int(os.environ.get("MAX_DOMAIN_STRICT_CHARS", "3400"))
MAX_AUTHOR_STRICT_CHARS = int(os.environ.get("MAX_AUTHOR_STRICT_CHARS", "900"))
MAX_FOCUS_STRICT_CHARS = int(os.environ.get("MAX_FOCUS_STRICT_CHARS", "480"))

# --- 上下文管理配置 ---
# 长连载增强：提高上下文目标上限，减少中后期被动裁剪导致的遗忘
MAX_CONTEXT_BYTES = 12000 # 上下文文件目标最大字节数
VOLUME_CHAPTER_SIZE = 20
MAX_PENDING_HOOKS = 40
MAX_VOLUME_SUMMARIES = 12

# 默认故事上下文结构
DEFAULT_CONTEXT = {
    "last_generated_chapter": 0,
    "protagonist_info": {
        "name": "Unknown",
        "description": "",
        "key_items_abilities": [],
        "key_relationships": {}
    },
    "world_setting": {
        "description": "",
        "key_elements": []
    },
    "core_characters": [],  # 新增：核心配角列表
    "core_items": [],       # 新增：核心道具列表
    "recent_plot_summary": "",
    # 长连载增强：保留最近多章的结尾摘要，作为滚动记忆
    "recent_chapter_summaries": [],
    # 长连载增强：未回收线索池（伏笔/承诺/悬念）
    "pending_hooks": [],
    # 长连载增强：分卷摘要
    "volume_summaries": []
}

# --- AI 相关配置 ---
# AI 模型名称
# 可分别覆写，不设置则使用当前 provider 的 DEFAULT_LLM_MODEL
STYLE_ANALYSIS_MODEL = os.environ.get("STYLE_ANALYSIS_MODEL", DEFAULT_LLM_MODEL)
CHAPTER_GENERATION_MODEL = os.environ.get("CHAPTER_GENERATION_MODEL", DEFAULT_LLM_MODEL)
CONTEXT_ANALYSIS_MODEL = os.environ.get("CONTEXT_ANALYSIS_MODEL", DEFAULT_LLM_MODEL)

# AI 请求参数
# 分析上下文时，为了确保 JSON 完整性，token 限制设大一些
CONTEXT_ANALYSIS_MAX_TOKENS = 4096 
CONTEXT_ANALYSIS_TEMPERATURE = 0.05

# 生成章节温度：过低时句式易过于整齐，易被各平台判为「AI 特征偏高」。
# 默认略调高以增加错落感；需要更稳的输出可设环境变量 CHAPTER_GENERATION_TEMPERATURE=0.2
CHAPTER_GENERATION_TEMPERATURE = float(os.environ.get("CHAPTER_GENERATION_TEMPERATURE", "0.58"))
# 章节期望字数由 --length 控制；实际 API 的 max_tokens 在 ai_handler 中按字数换算（中文约 2 token/字），勿把字数直接当 max_tokens。

# 风格分析时的参数
STYLE_ANALYSIS_MAX_TOKENS = 4096
STYLE_ANALYSIS_TEMPERATURE = 0.05

# --- 其他配置 ---
# 处理章节内容时传递给 AI 的最大字符数，防止输入过长
MAX_CHAPTER_CONTENT_LENGTH = 6000

# 项目定位为「同结构改编」：严格跟 input 参考章结构骨架；衔接上一章读原作、生成后不把生成稿反写进设定。
# 默认开启。实验/同人自由续写可设 STRICT_SOURCE_PLOT=0 或命令行 --no_strict_source_plot。
STRICT_SOURCE_PLOT = os.environ.get("STRICT_SOURCE_PLOT", "1").strip() in {"1", "true", "True", "YES", "yes"}

# 实体改写（角色/地名/事件/物件名全局换名）：默认开启，深度降重。
# 关闭可设 ENTITY_REWRITE=0 或命令行 --no_entity_rewrite。
ENTITY_REWRITE = os.environ.get("ENTITY_REWRITE", "1").strip() in {"1", "true", "True", "YES", "yes"}

# --- 降低 AI 味道配置 ---
ENABLE_ANTI_AI_REWRITE = True
ANTI_AI_MAX_ROUNDS = 2
AUDIT_MAX_REVISE_ROUNDS = 3
# 最后一轮若仅差少量分数，允许“近阈值放行”以避免长时间重跑后仍不落盘
AUDIT_NEAR_PASS_DELTA = 3

# --- 参考相似度与结构骨架贴合 ---
# 可被 audit_rules.json 覆盖；这里提供环境变量默认值，便于不同题材/长度快速调参。
REFERENCE_SIMILARITY_NGRAM_OVERLAP = float(os.environ.get("REFERENCE_SIMILARITY_NGRAM_OVERLAP", "0.045"))
REFERENCE_SIMILARITY_SENTENCE_REUSE = float(os.environ.get("REFERENCE_SIMILARITY_SENTENCE_REUSE", "0.08"))
REFERENCE_SIMILARITY_OVERLAP_COUNT = int(os.environ.get("REFERENCE_SIMILARITY_OVERLAP_COUNT", "80"))
PLOT_FIDELITY_MIN_SCORE = int(os.environ.get("PLOT_FIDELITY_MIN_SCORE", "80"))

# --- 文件增长治理（参考 inkos 的保留窗口/压缩思路） ---
# runtime 目录仅保留最近 N 章的工件（intent/context/trace）
MAX_RUNTIME_CHAPTER_ARTIFACTS = 40
# 单个 runtime intent 文件最大字符（超出截断）
MAX_RUNTIME_INTENT_CHARS = 4000
# 单个 runtime context 快照最大字节（超出降载写入）
MAX_RUNTIME_CONTEXT_SNAPSHOT_BYTES = 12000
# pruned_context_archive 的历史保留上限
MAX_PRUNED_ARCHIVE_ABILITIES = 200
MAX_PRUNED_ARCHIVE_ELEMENTS = 200
MAX_PRUNED_ARCHIVE_RELATIONSHIPS = 200

# --- 自动知识同步 ---
# 章节完成后自动更新 story_domain（无需人工审核）
AUTO_UPDATE_DOMAIN_KNOWLEDGE = True

# --- LLM 调试日志 ---
# 开启后会打印每次请求的接口路径与响应预览，便于定位“模型到底返回了什么”
DEBUG_LLM_LOG = os.environ.get("DEBUG_LLM_LOG", "1").strip() in {"1", "true", "True", "YES", "yes"}
DEBUG_LLM_PREVIEW_CHARS = int(os.environ.get("DEBUG_LLM_PREVIEW_CHARS", "600"))

# 豆包调用路径策略：
# 0 = 默认走 OpenAI 兼容 chat.completions（更稳，适合本项目文本生成/JSON审计）
# 1 = 优先走 Ark /responses（可能返回 reasoning 文本，适合特定场景）
DOUBAO_USE_RESPONSES_API = os.environ.get("DOUBAO_USE_RESPONSES_API", "0").strip() in {"1", "true", "True", "YES", "yes"}
