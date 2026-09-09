"""
config.py —— 全局配置文件
================================
作用：集中管理 API 密钥、模型名称等配置。
密钥从环境变量读取，避免硬编码泄露（.gitignore 时也安全）。

使用方法（二选一）：
  方式1（推荐，临时设置）:
    PowerShell:  $env:LLM_API_KEY="sk-xxxx"
  方式2（长期）:
    在项目根目录新建 .env 文件，写入:
      LLM_API_KEY=sk-xxxx
      LLM_BASE_URL=https://api.deepseek.com
"""

import os

# ---------------------------------------------------------------
# 一、LLM API 配置
# ---------------------------------------------------------------
# API 密钥：优先从环境变量读取，读不到再从 .env 文件读取
API_KEY = os.environ.get("LLM_API_KEY", "")

# API 地址（兼容 OpenAI 格式的服务都可用）：
#   DeepSeek: https://api.deepseek.com         （便宜，推荐开发调试）
#   智谱GLM:  https://open.bigmodel.cn/api/paas/v4
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")

# 默认模型名
#   DeepSeek: deepseek-chat
#   智谱GLM:  glm-4-flash（有免费额度，适合开发）
MODEL_NAME = os.environ.get("LLM_MODEL", "deepseek-chat")

# ---------------------------------------------------------------
# 一之二、Semantic Scholar API 密钥（检索Agent用）
# ---------------------------------------------------------------
# 免费申请: https://www.semanticscholar.org/product/api#form
# 有密钥后限流额度大幅提升（1次/秒 独享），匿名模式经常429卡死
# 留空 = 匿名模式（能用但不稳定）
S2_API_KEY = os.environ.get("S2_API_KEY", "")

# ---------------------------------------------------------------
# 一之三、应用访问密码（云端部署防护）
# ---------------------------------------------------------------
# 部署到公网后启用：陌生访客打开网页必须先输密码，否则会消耗你的
# LLM API 额度（流水线一次跑下来要调用几十次模型，按字数计费）
# 留空 = 不启用密码门（本地开发时留空即可）
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# ---------------------------------------------------------------
# 二、各Agent的温度参数（temperature）
# ---------------------------------------------------------------
# 温度越低输出越稳定。提取/审查任务要求"忠实原文"，用 0.1；
# 规划任务需要一点发散性，用 0.5。
TEMP_PLANNER = 0.5     # 规划Agent：任务分解需要发散
TEMP_EXTRACTOR = 0.1   # 提取Agent：信息抽取要求严格忠实原文
TEMP_REVIEWER = 0.1    # 审查Agent：判定结果要求稳定可复现
TEMP_SYNTHESIZER = 0.3 # 综合Agent：写综述允许少量文采

# ---------------------------------------------------------------
# 三、项目路径
# ---------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PAPER_DIR = os.path.join(PROJECT_ROOT, "papers")  # 下载的PDF存放处
DATA_DIR = os.path.join(PROJECT_ROOT, "data")     # 证据库JSON存放处
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output") # 综合Agent的产出目录(表格/图谱/报告)

# ---------------------------------------------------------------
# 四、如果 .env 文件存在，则加载其中的配置（简易版，无需额外依赖）
# ---------------------------------------------------------------
# 加载顺序: 先读环境变量(os.environ), 再读.env文件补充缺失项
# 规则: 环境变量 > .env 文件 > 默认值（环境变量优先级最高）
_env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    with open(_env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过注释行和空行
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                # 环境变量中已有该键则跳过（环境变量优先级 > .env）
                if key in os.environ:
                    continue
                if key == "LLM_API_KEY":
                    API_KEY = value
                elif key == "LLM_BASE_URL":
                    BASE_URL = value
                elif key == "LLM_MODEL":
                    MODEL_NAME = value
                elif key == "S2_API_KEY":
                    S2_API_KEY = value
                elif key == "APP_PASSWORD":
                    APP_PASSWORD = value
