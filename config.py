import os

# --- API 和路径配置 ---
# 尝试从环境变量获取 API Key，如果未设置，则使用占位符
# 在实际使用中，请确保设置了 DEEPSEEK_API_KEY 环境变量
API_KEY = 'sk-1c6c5c08ade4448690f5b4d2358eaf6a'
BASE_URL = "https://api.deepseek.com/v1"

# 文件路径
CONTEXT_FILE = 'story_context.json'
PRUNED_ARCHIVE_FILE = 'pruned_context_archive.json'
DEFAULT_INPUT_DIR = '1-50' # 默认原始章节输入目录
DEFAULT_OUTPUT_DIR = 'output_chapters' # 默认生成章节输出目录

# --- 上下文管理配置 ---
MAX_CONTEXT_BYTES = 3000 # 上下文文件目标最大字节数

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
    "recent_plot_summary": ""
}

# --- AI 相关配置 ---
# AI 模型名称
STYLE_ANALYSIS_MODEL = "deepseek-chat"
CHAPTER_GENERATION_MODEL = "deepseek-chat"
CONTEXT_ANALYSIS_MODEL = "deepseek-chat"

# AI 请求参数
# 分析上下文时，为了确保 JSON 完整性，token 限制设大一些
CONTEXT_ANALYSIS_MAX_TOKENS = 4096 
CONTEXT_ANALYSIS_TEMPERATURE = 0.1

# 生成章节时，可以有更高的创造性
CHAPTER_GENERATION_TEMPERATURE = 0.1
# 注意：章节生成长度由命令行参数 --length 控制，这里不设置 max_tokens

# 风格分析时的参数
STYLE_ANALYSIS_MAX_TOKENS = 4096
STYLE_ANALYSIS_TEMPERATURE = 0.1

# --- 其他配置 ---
# 处理章节内容时传递给 AI 的最大字符数，防止输入过长
MAX_CHAPTER_CONTENT_LENGTH = 6000
