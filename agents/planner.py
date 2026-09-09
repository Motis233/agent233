"""
planner.py —— 规划Agent
================================
职责：把用户输入的研究主题（中文或英文）分解为结构化的检索计划：
  - 多组英文检索词（arXiv是英文库，中文主题必须翻译+扩展）
  - 论文筛选标准
  - 目标论文数

输入: 用户的自然语言主题，如 "调研SNN的训练方法"
输出: models.SearchPlan 实例
"""

import llm_client
from models import SearchPlan
import config

# 规划Agent的系统提示词（角色设定 + 任务要求）
PLANNER_SYSTEM_PROMPT = """你是一位经验丰富的科研文献调研规划专家。

你的任务：把用户给出的研究主题，转化成一个高质量的arXiv文献检索计划。

要求：
1. keywords：生成恰好**4组**英文检索词（arXiv只收录英文论文）。
   - 必须覆盖主题的不同角度。经典论文的召回率取决于角度覆盖度，
     推荐组合（按主题灵活调整）:
     a. 核心主题的通用术语组合（如 "spiking neural network training"）
     b. 领域主流方法的名称（如 "surrogate gradient SNN"、
        "backpropagation spiking"）
     c. 综述/survey角度（如 "spiking neural network survey"，
        能召回领域综述=召回其引用的经典论文线索）
     d. 标准工具/框架/基准名称（如 "SpikingJelly"、"neuromorphic
        Loihi benchmark"）——经典论文标题常含专有名词，
        通用术语检索匹配不到它们
   - 必须使用该领域的**标准英文术语**（如"脉冲神经网络"的标准术语是
     "spiking neural network"，而不是"pulse neural network"）
   - 每组检索词是空格分隔的关键词组合，适合学术库标题+摘要检索
   - 中文主题必须先翻译成英文专业术语
2. classic_titles：列出该领域**公认奠基/经典论文的精确英文标题**
   （5-8篇，宁缺毋滥，只列教科书级/高被引开山之作，如
   "SpikeProp: backpropagation for networks of spiking neurons"）。
   背景说明：这些老论文的摘要不含现代检索词，关键词检索系统性地
   召回不到它们，而学术数据库的引用图谱又常有缺失——你的领域知识
   是召回它们的最后手段。标题必须尽量精确（逐字引用原标题），
   不确定的不要列。
3. inclusion_criteria：制定筛选标准，通常包含：年份范围（综述类调研
   建议"近10年"而非"近5年"——经典奠基论文往往发表较早）、相关性
   要求、是否需要有实验验证的论文（排除纯理论/纯灌水）
4. target_count：目标论文数，必须是一个单独的整数（如10或15，不要写区间），
   小规模试点用5-10篇，正式调研用15-20篇
"""


def make_plan(topic: str) -> SearchPlan:
    """
    生成检索计划

    参数:
        topic: 用户输入的研究主题（中英文均可）

    返回:
        SearchPlan 实例（含检索词、筛选标准、目标篇数）
    """
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": f"我要调研的研究主题是：{topic}"},
    ]

    # 规划任务用较高温度(0.5)，需要发散性思维
    plan = llm_client.chat_json(
        messages,
        schema_class=SearchPlan,
        temperature=config.TEMP_PLANNER,
    )

    print(f"[规划Agent] 主题: {topic}")
    print(f"[规划Agent] 检索词: {plan.keywords}")
    print(f"[规划Agent] 经典论文清单: {plan.classic_titles}")
    print(f"[规划Agent] 筛选标准: {plan.inclusion_criteria}")
    print(f"[规划Agent] 目标篇数: {plan.target_count}")
    return plan


# ---------------------------------------------------------------
# 单独运行本文件的测试入口
# ---------------------------------------------------------------
if __name__ == "__main__":
    plan = make_plan("脉冲神经网络的高效训练方法")
    llm_client.print_usage()
