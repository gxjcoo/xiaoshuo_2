import os

# --- API 和路径配置 ---
# 尝试从环境变量获取 API Key，如果未设置，则使用占位符
# 在实际使用中，请确保设置了 DEEPSEEK_API_KEY 环境变量
API_KEY = 'sk-1c6c5c08ade4448690f5b4d2358eaf6a'
BASE_URL = "https://api.deepseek.com/v1"

# HTTP 超时（秒）。未设置时 httpx 可能长时间无响应，看起来像「卡住」。
# 生成长章节若超时，可调大环境变量 API_HTTP_READ_TIMEOUT，或在 config 里改默认值。
API_HTTP_CONNECT_TIMEOUT = float(os.environ.get("API_HTTP_CONNECT_TIMEOUT", "30"))
API_HTTP_READ_TIMEOUT = float(os.environ.get("API_HTTP_READ_TIMEOUT", "300"))

# 文件路径
CONTEXT_FILE = 'story_context.json'
PRUNED_ARCHIVE_FILE = 'pruned_context_archive.json'
DEFAULT_INPUT_DIR = '1-50' # 默认原始章节输入目录
DEFAULT_OUTPUT_DIR = 'output_chapters' # 默认生成章节输出目录

# DDD / SDD：静态领域与章节规格目录（相对项目工作目录）
STORY_DOMAIN_DIR = 'story_domain'
CHAPTER_SPECS_DIR = 'chapter_specs'
RUNTIME_DIR = 'runtime'
AUTHOR_INTENT_FILE = 'author_intent.md'
CURRENT_FOCUS_FILE = 'current_focus.md'
# 注入提示词时的长度上限（字符），避免超出模型上下文
MAX_DOMAIN_PROMPT_CHARS = 8000
MAX_CHAPTER_SPEC_CHARS = 6000
MAX_AUTHOR_INTENT_CHARS = 3000
MAX_CURRENT_FOCUS_CHARS = 2000

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
STYLE_ANALYSIS_MODEL = "deepseek-chat"
CHAPTER_GENERATION_MODEL = "deepseek-chat"
CONTEXT_ANALYSIS_MODEL = "deepseek-chat"

# AI 请求参数
# 分析上下文时，为了确保 JSON 完整性，token 限制设大一些
CONTEXT_ANALYSIS_MAX_TOKENS = 4096 
CONTEXT_ANALYSIS_TEMPERATURE = 0.05

# 生成章节温度：过低时句式易过于整齐，易被各平台判为「AI 特征偏高」。
# 默认略调高以增加错落感；需要更稳的输出可设环境变量 CHAPTER_GENERATION_TEMPERATURE=0.2
CHAPTER_GENERATION_TEMPERATURE = float(os.environ.get("CHAPTER_GENERATION_TEMPERATURE", "0.55"))
# 注意：章节生成长度由命令行参数 --length 控制，这里不设置 max_tokens

# 风格分析时的参数
STYLE_ANALYSIS_MAX_TOKENS = 4096
STYLE_ANALYSIS_TEMPERATURE = 0.05

# --- 其他配置 ---
# 处理章节内容时传递给 AI 的最大字符数，防止输入过长
MAX_CHAPTER_CONTENT_LENGTH = 6000

# --- 降低 AI 味道配置 ---
ENABLE_ANTI_AI_REWRITE = True
ANTI_AI_MAX_ROUNDS = 2

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
