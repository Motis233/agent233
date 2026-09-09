"""
qa_agent.py —— 可信问答Agent（方案二：Evidence-Bounded QA）
================================
职责：
  只基于"已通过两级核验的声明池"回答用户问题，
  证据不足时明确拒答——宁可拒答，不可编造。

【设计理念（与普通AI问答的本质区别）】
  普通问答（ChatGPT/Consensus）: 用海量预训练知识回答，
    无法区分"来自文献的证据"和"模型的编造"。
  本Agent（证据约束问答）:
    1. 知识库 = 审查Agent判定 supported 的声明（每条带原文引用）
    2. 回答必须标注来源 [声明#N]
    3. 证据不足 → 结构化拒答（说明缺什么证据）
  "拒答能力"本身是卖点：它证明系统对幻觉的克制。

输入: 用户问题 + data/下的声明池文件
输出: QAAnswer(回答文本 + 使用的声明ID列表 + 是否拒答)
"""

import os
import json

import llm_client
import config
from pydantic import BaseModel, Field


class QAAnswer(BaseModel):
    """一次问答的结构化输出"""
    can_answer: bool = Field(
        description="声明池中的证据是否足以回答问题。"
                    "注意: 部分回答(能答一半)也算true，完全无法回答才是false"
    )
    answer: str = Field(
        description="基于声明的回答正文。每句话后标注来源[声明#N]。"
                    "can_answer=false时填写'当前证据库无法回答该问题。'"
    )
    used_claims: list[int] = Field(
        description="回答中实际引用的声明编号列表(如[3,7])。拒答时空列表"
    )
    missing: str = Field(
        description="can_answer=false时: 说明缺什么类型的证据才能回答;"
                    "can_answer=true时: 填空字符串"
    )


# ---------------------------------------------------------------
# 声明池构建
# ---------------------------------------------------------------
def build_claim_pool() -> list[dict]:
    """
    从 data/ 构建已核验的声明池

    数据流: paper_cards.json(全部声明) + review_results.json(核验结果)
          -> 只保留 verdict==supported 的声明

    返回:
        [{"num": 1, "arxiv_id": ..., "content": ..., "type": ...,
          "paper_title": ...}, ...]
        num 从1开始编号（对话中引用 [声明#N] 用）
    """
    cards_path = os.path.join(config.DATA_DIR, "paper_cards.json")
    review_path = os.path.join(config.DATA_DIR, "review_results.json")
    if not os.path.exists(cards_path) or not os.path.exists(review_path):
        return []

    cards = json.load(open(cards_path, encoding="utf-8"))
    reviews = json.load(open(review_path, encoding="utf-8"))

    # 核验通过的声明key集合
    supported = {
        f"{r['arxiv_id']}#{r['claim_index']}"
        for r in reviews
        if (r.get("verdict") or {}).get("verdict") == "supported"
    }

    pool = []
    for card in cards:
        for idx, claim in enumerate(card.get("claims", [])):
            if f"{card['arxiv_id']}#{idx}" not in supported:
                continue
            pool.append({
                "num": len(pool) + 1,
                "arxiv_id": card["arxiv_id"],
                "paper_title": card.get("title", "")[:60],
                "year": card.get("year"),
                "type": claim.get("claim_type"),
                "content": claim.get("content", ""),
            })
    return pool


def _format_pool(pool: list[dict]) -> str:
    """把声明池格式化为Prompt里的文本块"""
    lines = []
    for c in pool:
        lines.append(
            f"[声明#{c['num']}] ({c['type']}, 论文《{c['paper_title']}》"
            f"arXiv:{c['arxiv_id']}, {c['year']}年)\n{c['content']}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------
# 核心问答函数
# ---------------------------------------------------------------
QA_SYSTEM_PROMPT = """你是严格的文献问答助手，只基于给定的<已核验声明池>回答问题。

【回答规则】
1. 只能使用声明池里的信息，绝对不能使用你自己的知识补充
2. 每个事实性陈述后标注来源，格式如 [声明#3]
3. 可以综合多条声明回答，但每条引用的声明必须真实支撑该陈述
4. 声明池里没有的信息，无论你多确定，都不能说

【重要: 宽容判定】
只要声明池里有与问题主题相关的声明（哪怕只是部分相关），
就应该 can_answer=true 并基于这些声明回答——
比如问"X的核心方法"，池里有X的方法类声明，就必须回答它。
问得宽泛时（如"各自的方法"），把池中所有相关声明都列出来。
不能因为"声明没有完美覆盖问题的每个细节"就拒答。

【拒答规则（仅当声明池完全无相关内容时）】
- can_answer 设为 false
- answer 填"当前证据库无法回答该问题。"
- missing 说明需要什么证据

【部分可答的情况】
如果问题有一部分能答、另一部分不能，can_answer=true，
能答的部分正常回答，并在回答末尾注明"注: 关于XX部分，当前证据库无相关数据"。"""


def answer_question(question: str, history: list[dict] | None = None
                    ) -> tuple[QAAnswer, list[dict]]:
    """
    回答用户问题（证据约束问答）

    参数:
        question: 用户问题
        history: 对话历史 [{"role":..., "content":...}, ...]（可选）

    返回:
        (QAAnswer结构化答案, 本次使用的声明池) —— 声明池一并返回
        供前端展示"本次回答依据的声明"
    """
    pool = build_claim_pool()
    if not pool:
        return QAAnswer(
            can_answer=False,
            answer="当前没有已核验的声明池，请先运行完整流水线。",
            used_claims=[],
            missing="需要先运行流水线生成已核验声明",
        ), []

    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT},
        {"role": "user",
         "content": f"<已核验声明池>\n{_format_pool(pool)}\n</已核验声明池>\n\n"
                    f"用户问题: {question}"},
    ]
    # 简单的多轮支持：把最近2轮历史插到当前问题前
    if history:
        for h in history[-4:]:
            messages.insert(1, h)

    ans = llm_client.chat_json(messages, QAAnswer, temperature=0.1)
    return ans, pool


# ---------------------------------------------------------------
# 拒答测试（独立的实验价值：量化系统的可信度）
# ---------------------------------------------------------------
def run_refusal_test() -> dict:
    """
    拒答能力测试（E5实验）:
      - 可答组: 问题答案明确在声明池里 → 应正常回答
      - 拒答组: 问题答案不在池里(知识库外/未核验内容) → 应拒答

    返回: {"answerable_acc": ..., "refusal_acc": ..., "details": [...]}
    """
    pool = build_claim_pool()
    if not pool:
        print("[问答Agent] 无声明池，跳过测试")
        return {}

    # ---- 构造测试问题 ----
    # 可答组: 从声明池里抽3条声明反向提问（问题即声明内容的问句化）
    test_cases = []
    for c in pool[:3]:
        test_cases.append({
            "q": f"关于{c['paper_title'][:30]}这篇论文，{c['content'][:50]}... "
                 f"请具体说明它的相关情况",
            "expect": True,  # 应能回答
        })
    # 可答组补充: "核心方法"类问题（曾误判拒答的回归测试）
    #   取一篇有method声明的论文，用论文短名直接问方法
    method_claims = [c for c in pool if c["type"] == "method"]
    if method_claims:
        short_name = method_claims[0]["paper_title"].split(":")[0].strip()
        test_cases.append({
            "q": f"{short_name}的核心方法是什么？",
            "expect": True,
        })
    # 拒答组: 知识库外的问题（与当前论文池完全无关的领域）
    out_of_scope = [
        "Transformer的自注意力机制是怎么计算的？",
        "CRISPR基因编辑技术的原理是什么？",
        "量子计算中的qubit和经典bit的本质区别是什么？",
    ]
    for q in out_of_scope:
        test_cases.append({"q": q, "expect": False})  # 应拒答

    print(f"[问答Agent] 拒答测试: {len(test_cases)}个问题 "
          f"({sum(1 for t in test_cases if t['expect'])}可答/"
          f"{sum(1 for t in test_cases if not t['expect'])}应拒答)")

    details = []
    correct = 0
    for t in test_cases:
        ans, _ = answer_question(t["q"])
        # 判定: 期望可答且can_answer=true / 期望拒答且can_answer=false
        ok = (ans.can_answer == t["expect"])
        if ok:
            correct += 1
        details.append({
            "question": t["q"][:60],
            "expect_answerable": t["expect"],
            "actual_answerable": ans.can_answer,
            "correct": ok,
            "answer_preview": ans.answer[:80],
        })
        mark = "✓" if ok else "✗"
        print(f"  {mark} {'应答' if t['expect'] else '应拒'} -> "
              f"{'答了' if ans.can_answer else '拒答'} | {t['q'][:40]}")

    n_answerable = sum(1 for t in test_cases if t["expect"])
    n_refusal = len(test_cases) - n_answerable
    acc = correct / len(test_cases) if test_cases else 0
    print(f"[问答Agent] 测试通过率: {correct}/{len(test_cases)} = {acc:.0%}")
    return {
        "answerable_acc": (sum(1 for d in details
                               if d["expect_answerable"] and d["correct"])
                           / max(n_answerable, 1)),
        "refusal_acc": (sum(1 for d in details
                            if not d["expect_answerable"] and d["correct"])
                        / max(n_refusal, 1)),
        "overall": acc,
        "details": details,
    }


if __name__ == "__main__":
    # 独立测试
    result = run_refusal_test()
    if result:
        print(f"\n可答组正确率: {result['answerable_acc']:.0%}")
        print(f"拒答组正确率: {result['refusal_acc']:.0%}")
