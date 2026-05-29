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
# 可选: "mimo" | "deepseek" | "doubao"
# 优先使用环境变量覆盖，便于在不同机器/环境切换
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mimo").strip().lower()

if LLM_PROVIDER == "doubao":
    # 豆包（火山方舟 Ark）配置
    API_KEY = os.environ.get("DOUBAO_API_KEY", os.environ.get("ARK_API_KEY", ""))
    BASE_URL = os.environ.get("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    DEFAULT_LLM_MODEL = os.environ.get("DOUBAO_MODEL", "doubao-seed-2-0-pro-260215")
elif LLM_PROVIDER == "mimo":
    # MiMo（小米大模型）配置
    API_KEY = os.environ.get("MIMO_API_KEY", os.environ.get("API_KEY", ""))
    BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    DEFAULT_LLM_MODEL = os.environ.get("MIMO_MODEL", "MiMo-V2.5-Pro")
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

RUNTIME_DIR = 'runtime'
CURRENT_FOCUS_FILE = 'current_focus.md'
AUDIT_RULES_FILE = 'audit_rules.json'
# 注入提示词时的长度上限（字符），避免超出模型上下文
MAX_CURRENT_FOCUS_CHARS = 2000
# 严格结构适配（STRICT_SOURCE_PLOT）时进一步压缩，减轻「说明书」式上下文抬高 AI 率
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

# 章节间等待秒数：串行批量跑时在相邻两章之间暂停，避免触发 API rate limit。
# 默认 5 秒；调试时可设为 0 加快迭代；大批量可适当调大。
INTER_CHAPTER_SLEEP = int(os.environ.get("INTER_CHAPTER_SLEEP", "5"))

# --- 降低 AI 味道配置 ---
ENABLE_ANTI_AI_REWRITE = True
ANTI_AI_MAX_ROUNDS = 2
AUDIT_MAX_REVISE_ROUNDS = 3
# 性能开关：审计阶段的规则审计与结构贴合审计彼此独立，默认并行请求以减少单轮等待。
AUDIT_PARALLEL_EVALUATORS = os.environ.get("AUDIT_PARALLEL_EVALUATORS", "1").strip() in {"1", "true", "True", "YES", "yes"}
# 性能开关：确定性跨章衔接守卫已发现硬冲突时，默认跳过昂贵的 LLM 衔接复审。
AUDIT_SKIP_LLM_CONTINUITY_ON_GUARD_FAIL = os.environ.get("AUDIT_SKIP_LLM_CONTINUITY_ON_GUARD_FAIL", "1").strip() in {"1", "true", "True", "YES", "yes"}
# 性能开关：去 AI 味修订只在 ai_trace 真正低于硬阈值时触发，避免已达标章节反复长文本改写。
ANTI_AI_REWRITE_ONLY_WHEN_BELOW_THRESHOLD = os.environ.get("ANTI_AI_REWRITE_ONLY_WHEN_BELOW_THRESHOLD", "1").strip() in {"1", "true", "True", "YES", "yes"}
# 性能开关：正文生成已要求模型输出章节标题，默认复用该标题，避免额外标题 API。
ENABLE_LLM_TITLE_GENERATION = os.environ.get("ENABLE_LLM_TITLE_GENERATION", "0").strip() in {"1", "true", "True", "YES", "yes"}
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


# --- LLM 调试日志 ---
# 开启后会打印每次请求的接口路径与响应预览，便于定位“模型到底返回了什么”
DEBUG_LLM_LOG = os.environ.get("DEBUG_LLM_LOG", "0").strip() in {"1", "true", "True", "YES", "yes"}
DEBUG_LLM_PREVIEW_CHARS = int(os.environ.get("DEBUG_LLM_PREVIEW_CHARS", "600"))

# 豆包调用路径策略：
# 0 = 默认走 OpenAI 兼容 chat.completions（更稳，适合本项目文本生成/JSON审计）
# 1 = 优先走 Ark /responses（可能返回 reasoning 文本，适合特定场景）
DOUBAO_USE_RESPONSES_API = os.environ.get("DOUBAO_USE_RESPONSES_API", "0").strip() in {"1", "true", "True", "YES", "yes"}


# --- 工作流配置 ---
# 工作流状态文件路径
WORKFLOW_STATE_FILE = os.environ.get("WORKFLOW_STATE_FILE", "workflow_state.json")

# 拆书分析配置
# 采样策略：前N章
DECOMPOSE_SAMPLE_FRONT = int(os.environ.get("DECOMPOSE_SAMPLE_FRONT", "3"))
# 采样策略：中间N章
DECOMPOSE_SAMPLE_MIDDLE = int(os.environ.get("DECOMPOSE_SAMPLE_MIDDLE", "2"))
# 采样策略：末尾N章
DECOMPOSE_SAMPLE_END = int(os.environ.get("DECOMPOSE_SAMPLE_END", "2"))
# 拆书输出文件
DECOMPOSE_OUTPUT_FILE = os.environ.get("DECOMPOSE_OUTPUT_FILE", "book_profile.json")
# 拆书分析时每次 LLM 调用的最大字符数
DECOMPOSE_MAX_CHARS_PER_CALL = int(os.environ.get("DECOMPOSE_MAX_CHARS_PER_CALL", "15000"))
# 拆书分析使用的模型（默认使用上下文分析模型）
DECOMPOSE_MODEL = os.environ.get("DECOMPOSE_MODEL", DEFAULT_LLM_MODEL)

# 高级拆书配置（适用于长篇小说）
# 是否启用高级拆书模式（自动检测长篇小说）
DECOMPOSE_ADVANCED_AUTO = os.environ.get("DECOMPOSE_ADVANCED_AUTO", "1").strip() in {"1", "true", "True", "YES", "yes"}
# 启用高级拆书的字数阈值
DECOMPOSE_ADVANCED_THRESHOLD = int(os.environ.get("DECOMPOSE_ADVANCED_THRESHOLD", "500000"))
# 高级拆书模式下，快速扫描章节数
DECOMPOSE_ADVANCED_QUICK_SCAN = int(os.environ.get("DECOMPOSE_ADVANCED_QUICK_SCAN", "15"))
# 高级拆书模式下，每个维度深度分析章节数
DECOMPOSE_ADVANCED_DEEP_PER_DIM = int(os.environ.get("DECOMPOSE_ADVANCED_DEEP_PER_DIM", "5"))
# 高级拆书模式下，伏笔分析使用的最大字符数（需要全书视野）
DECOMPOSE_ADVANCED_FORESHADOW_MAX_CHARS = int(os.environ.get("DECOMPOSE_ADVANCED_FORESHADOW_MAX_CHARS", "30000"))

# 工作流自动跳过已完成任务
WORKFLOW_AUTO_SKIP = os.environ.get("WORKFLOW_AUTO_SKIP", "1").strip() in {"1", "true", "True", "YES", "yes"}

# 连贯性检查配置
# 连贯性检查最低得分阈值（低于此值会发出警告）
CONTINUITY_CHECK_MIN_SCORE = int(os.environ.get("CONTINUITY_CHECK_MIN_SCORE", "70"))
# 连贯性检查使用的最大字符数
CONTINUITY_CHECK_MAX_CHARS = int(os.environ.get("CONTINUITY_CHECK_MAX_CHARS", "4000"))

# 伏笔管理配置
# 最大未回收伏笔数量
MAX_PENDING_FORESHADOWS = int(os.environ.get("MAX_PENDING_FORESHADOWS", "20"))
# 伏笔分析使用的最大字符数
FORESHADOW_ANALYSIS_MAX_CHARS = int(os.environ.get("FORESHADOW_ANALYSIS_MAX_CHARS", "4000"))

# 风格一致性验证配置
# 风格一致性最低得分阈值
STYLE_CONSISTENCY_MIN_SCORE = int(os.environ.get("STYLE_CONSISTENCY_MIN_SCORE", "70"))
# 风格一致性验证使用的最大字符数
STYLE_CONSISTENCY_MAX_CHARS = int(os.environ.get("STYLE_CONSISTENCY_MAX_CHARS", "3000"))

# 分卷处理配置
# 每卷章节数
VOLUME_SIZE = int(os.environ.get("VOLUME_SIZE", "20"))
