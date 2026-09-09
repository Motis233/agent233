"""
synthesizer.py —— 综合Agent
================================
职责（三件产出）：
  1. build_table()   : 只用【通过审查】的声明，按方法分类生成综述对比表格
  2. build_graph()   : 引用关系图谱（S2引用数据可达时用真实引用关系，
                       否则降级为"论文-方法分类"二部图，保证总有图可看）
  3. build_report()  : 汇总生成最终Markdown综述报告

核心设计原则——"审查结果驱动综合":
  只有 verdict=supported 且引用对齐成功的声明才进入综述。
  被判幻觉的声明进入报告附录的"被剔除声明"清单（透明可审计）。

输入: papers/cards/review_results（前三步的产出，均从data/读取）
输出: output/review_table.md, output/citation_graph.html, output/final_report.md
"""

import os
import json
import time

import requests

import llm_client
import config
from models import PaperMeta, PaperCard, ReviewResult

# 产出目录
OUTPUT_DIR = os.path.join(config.PROJECT_ROOT, "output")

# Semantic Scholar 引用关系API（拿"本文引用了谁"）
S2_REF_API = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}/references"
S2_REF_FIELDS = "title,externalIds"


# ---------------------------------------------------------------
# 工具：加载前三步的产出
# ---------------------------------------------------------------
def load_inputs():
    """从data/目录加载 papers_meta / paper_cards / review_results"""
    def _load(name, cls):
        path = os.path.join(config.DATA_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            return [cls(**item) for item in json.load(f)]

    papers = _load("papers_meta.json", PaperMeta)
    cards = _load("paper_cards.json", PaperCard)
    reviews = _load("review_results.json", ReviewResult)
    return papers, cards, reviews


def _verified_claims(cards: list[PaperCard],
                     reviews: list[ReviewResult]) -> dict[str, list]:
    """
    按论文分组返回"通过审查"的声明

    通过标准（与reviewer的幻觉判定协议严格互补）:
      quote_alignment=True 且 verdict=supported
    """
    # 先建索引: (arxiv_id, claim_index) -> ReviewResult
    review_idx = {(r.arxiv_id, r.claim_index): r for r in reviews}

    verified: dict[str, list] = {}
    for card in cards:
        good = []
        for idx, claim in enumerate(card.claims):
            r = review_idx.get((card.arxiv_id, idx))
            if r and r.quote_alignment and r.verdict.verdict == "supported":
                good.append(claim)
        verified[card.arxiv_id] = good
    return verified


# ---------------------------------------------------------------
# 产出1：综述对比表格
# ---------------------------------------------------------------
def build_table(cards: list[PaperCard],
                verified: dict[str, list]) -> str:
    """
    生成Markdown综述表格（每个方法分类一张子表）

    表格内容全部来自通过审查的声明——这是"防幻觉综述"的直接体现。
    """
    # 按方法分类分组
    categories: dict[str, list[PaperCard]] = {}
    for card in cards:
        categories.setdefault(card.method_category, []).append(card)

    lines = ["# 文献综述对比表格", ""]
    lines.append(f"> 共 {len(cards)} 篇论文，"
                 f"{sum(len(v) for v in verified.values())} 条已核验声明"
                 f"（仅收录通过两级审查的内容）")

    for cat, cat_cards in categories.items():
        lines.append(f"## 方法类别：{cat}")
        lines.append("")
        lines.append("| 论文 | 年份 | 核心方法 | 关键结果 | 局限性 |")
        lines.append("|------|------|----------|----------|--------|")
        for card in cat_cards:
            claims = verified.get(card.arxiv_id, [])
            method = next((c.content for c in claims
                           if c.claim_type == "method"), "（未通过核验）")
            result = next((c.content for c in claims
                           if c.claim_type == "result"), "（未通过核验）")
            limit = next((c.content for c in claims
                          if c.claim_type == "limitation"), "（未通过核验）")
            # 截断防止表格爆行
            lines.append(
                f"| {card.title[:40]}... | {card.year} "
                f"| {method[:60]} | {result[:60]} | {limit[:60]} |"
            )
        lines.append("")

    table_md = "\n".join(lines)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "review_table.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(table_md)
    print(f"[综合Agent] 综述表格已生成: {path}")
    return table_md


# ---------------------------------------------------------------
# 产出2：引用图谱
# ---------------------------------------------------------------
def _fetch_references(arxiv_id: str, max_retries: int = 3) -> list[str]:
    """
    从Semantic Scholar获取某论文的参考文献标题列表

    返回:
        引用论文的arXiv id列表（只保留同样是arXiv论文的引用，便于构图）;
        网络失败返回空列表（触发降级方案）
    """
    headers = {"x-api-key": config.S2_API_KEY} if config.S2_API_KEY else {}
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                S2_REF_API.format(arxiv_id=arxiv_id),
                params={"fields": S2_REF_FIELDS, "limit": 50},
                headers=headers, timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            ref_ids = []
            for item in data.get("data", []):
                ref_paper = item.get("citedPaper", {})
                ref_arxiv = (ref_paper.get("externalIds") or {}).get("ArXiv")
                if ref_arxiv:
                    ref_ids.append(ref_arxiv)
            return ref_ids
        except Exception:
            time.sleep(3)
    return []


def build_graph(papers: list[PaperMeta],
                cards: list[PaperCard]) -> str:
    """
    生成交互式引用图谱HTML（pyvis）

    图谱策略（两级降级，保证总有产出）:
      1. 首选: S2真实引用关系——检索到的论文之间的互引 + 引用外部论文
      2. 降级: S2不可达时，构建"论文-方法分类"二部图
         （论文节点连向它的方法类别节点，同样有分析价值）
    """
    import networkx as nx
    from pyvis.network import Network

    G = nx.DiGraph()
    graph_mode = "引用关系图"

    # 我们自己的论文集合（用于识别"内部互引"并高亮）
    our_ids = {p.arxiv_id for p in papers}
    title_by_id = {p.arxiv_id: p.title for p in papers}
    year_by_id = {p.arxiv_id: p.year for p in papers}

    # ---- 尝试真实引用关系（并行获取，串行需每篇1秒间隔+请求耗时）----
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        # 并行拉取所有论文的参考文献列表（保持与papers相同的顺序）
        all_refs = list(executor.map(lambda p: _fetch_references(p.arxiv_id),
                                     papers))

    ref_edges = 0
    for p, refs in zip(papers, all_refs):
        if not refs:
            continue  # 单篇失败不影响其他
        for ref_id in refs:
            if ref_id == p.arxiv_id:
                continue
            if ref_id in our_ids:
                # 内部互引：最有分析价值（谁引用了同批检索到的论文）
                G.add_edge(p.arxiv_id, ref_id, kind="internal")
                ref_edges += 1
            elif ref_edges < 40:  # 外部引用限量，防止图爆炸
                G.add_edge(p.arxiv_id, ref_id, kind="external")
                ref_edges += 1

    # ---- 降级方案：论文-方法分类二部图 ----
    if G.number_of_edges() == 0:
        graph_mode = "论文-方法分类二部图（S2引用数据不可达，自动降级）"
        print("[综合Agent] S2引用数据不可达，降级为论文-分类二部图")
        cat_by_id = {c.arxiv_id: c.method_category for c in cards}
        for p in papers:
            cat = cat_by_id.get(p.arxiv_id, "未分类")
            G.add_node(cat, kind="category")
            G.add_edge(p.arxiv_id, cat, kind="belongs")

    # ---- 节点属性（颜色区分身份）----
    color_map = {"internal": "#e74c3c", "external": "#bdc3c7",
                 "belongs": "#3498db"}
    for node in G.nodes():
        if node in our_ids:
            G.nodes[node]["color"] = "#2ecc71"          # 绿: 检索到的论文
            G.nodes[node]["title"] = (f"{title_by_id[node]} "
                                      f"({year_by_id[node]})")
            G.nodes[node]["size"] = 20
        elif G.nodes[node].get("kind") == "category":
            G.nodes[node]["color"] = "#f39c12"          # 橙: 方法分类
            G.nodes[node]["size"] = 15
        else:
            G.nodes[node]["color"] = "#95a5a6"          # 灰: 外部被引论文
            G.nodes[node]["size"] = 8
    for u, v, data in G.edges(data=True):
        data["color"] = color_map.get(data.get("kind"), "#bdc3c7")

    # ---- 渲染为交互式HTML ----
    net = Network(height="600px", width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#333333")
    net.from_nx(G)
    net.repulsion(node_distance=120, spring_length=150)
    net.show_buttons(filter_=["physics"])

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "citation_graph.html")
    net.write_html(path, notebook=False)
    print(f"[综合Agent] 图谱已生成: {path} (模式: {graph_mode}, "
          f"{G.number_of_nodes()}节点/{G.number_of_edges()}边)")
    return path


# ---------------------------------------------------------------
# 产出3：最终综述报告
# ---------------------------------------------------------------
SYNTH_SYSTEM_PROMPT = """你是一位严谨的学术综述撰写者。

你会收到一组论文的已核验信息（方法/结果/局限声明，均通过了两级忠实性审查）。

请撰写一篇结构化的中文综述章节，要求：
1. 按方法类别组织段落，每类说明核心思想、代表工作、优劣对比
   （不要输出章节大标题，系统会自动添加；直接以"#### 方法名"小节开始）
2. 只使用给你的信息，不得添加任何未提供的内容（这是防幻觉综述）
   ——材料中未出现的任何方法、数字、结论都严禁写入
3. 提及具体工作时用 [arXiv:编号] 标注，如 "SPIDE [arXiv:2302.00232]"
4. 末尾给出一段"趋势与开放问题"的总结（基于给定信息的合理推断，
   推断性语句用"可能/似乎"等限定词）
5. 篇幅400-600字
"""


def build_report(topic: str, cards: list[PaperCard],
                 verified: dict[str, list],
                 reviews: list[ReviewResult],
                 table_md: str, graph_path: str) -> str:
    """
    生成最终Markdown综述报告（LLM撰写正文 + 程序拼接统计与附录）
    """
    # ---- LLM撰写综述正文 ----
    material = []
    for card in cards:
        claims = verified.get(card.arxiv_id, [])
        if not claims:
            continue
        material.append(
            f"论文: {card.title} [arXiv:{card.arxiv_id}] ({card.year})\n"
            f"方法分类: {card.method_category}\n" +
            "\n".join(f"- [{c.claim_type}] {c.content}" for c in claims)
        )

    body = llm_client.chat(
        [{"role": "system", "content": SYNTH_SYSTEM_PROMPT},
         {"role": "user", "content": f"研究主题: {topic}\n\n" +
          "\n\n".join(material)}],
        temperature=config.TEMP_SYNTHESIZER,
    )

    # ---- 统计被剔除的声明（透明性附录）----
    hallucinated = [r for r in reviews
                    if not r.quote_alignment or r.verdict.verdict != "supported"]
    rejected_lines = "\n".join(
        f"- [{r.arxiv_id} #{r.claim_index}] {r.claim_content[:60]}... "
        f"(对齐={'Y' if r.quote_alignment else 'N'}, "
        f"判定={r.verdict.verdict})"
        for r in hallucinated
    ) or "（无）"

    total = len(reviews)
    good = total - len(hallucinated)

    # ---- 拼装最终报告 ----
    report = f"""# 研究综述：{topic}

> 本报告由"科研文献整理Agent"自动生成。
> 所有声明均通过两级忠实性审查（程序化引用对齐 + LLM语义核验），
> 未通过审查的内容已剔除并列入附录B，全程可审计。

## 一、方法分类与发展脉络

{body}

## 二、论文对比总表

{table_md.split('# 文献综述对比表格', 1)[-1].strip()}

## 三、引用图谱

见交互式图谱文件: `{os.path.basename(graph_path)}`
（绿色=本次检索论文, 红色箭头=检索集内部互引, 灰色=外部被引论文）

## 四、审查统计

| 指标 | 数值 |
|------|------|
| 收录论文 | {len(cards)} 篇 |
| 声明总数 | {total} 条 |
| 通过审查 | {good} 条 ({good / total:.0%}) |
| 剔除(幻觉) | {len(hallucinated)} 条 |
| **幻觉率** | **{len(hallucinated) / total:.1%}** |

## 附录B：被剔除的声明（审查透明性记录）

{rejected_lines}
"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "final_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[综合Agent] 最终报告已生成: {path}")
    return report


# ---------------------------------------------------------------
# 组合入口
# ---------------------------------------------------------------
def run(topic: str) -> dict:
    """
    综合Agent完整流水线: 加载数据 -> 表格 -> 图谱 -> 报告

    返回:
        dict(各产出文件路径)
    """
    papers, cards, reviews = load_inputs()
    verified = _verified_claims(cards, reviews)

    table_md = build_table(cards, verified)
    graph_path = build_graph(papers, cards)
    build_report(topic, cards, verified, reviews, table_md, graph_path)

    return {
        "table": os.path.join(OUTPUT_DIR, "review_table.md"),
        "graph": graph_path,
        "report": os.path.join(OUTPUT_DIR, "final_report.md"),
    }
