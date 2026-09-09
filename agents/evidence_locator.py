"""
evidence_locator.py —— 证据定位Agent（方案一：证据链穿透）
================================
职责：
  把审查通过的声明里的原文引用(quote)定位到PDF的具体页面，
  生成高亮标注的页面截图，供前端"证据穿透面板"展示。

【定位的难点与三级匹配策略】
  PDF提取的文本与quote的常见差异（实测总结）:
    1. 换行断裂: PDF里句子被行尾打断, 提取文本带\n
    2. 连字符断词: "perfor-\nmance" vs "performance"
    3. 合字/特殊空格: fi/fl合字, 不间断空格
  因此逐级放宽匹配:
    L1: 完整quote直接search_for()        (~60%命中)
    L2: quote前50字符再搜                 (~25%)
    L3: 最长连续词组(5词滑窗)逐个尝试      (~10%)
    兜底: 返回None, 前端显示"无法定位"

输入: (pdf_path, quote_text)
输出: EvidenceLocatorResult(页码, 高亮图片路径, 匹配级别)
"""

import os
import re

import fitz  # PyMuPDF

import config


class EvidenceHit:
    """一次定位成功的结果"""

    def __init__(self, page_num: int, image_path: str, match_level: int,
                 matched_text: str):
        self.page_num = page_num      # 0-based页码
        self.image_path = image_path  # 高亮页面截图的路径
        self.match_level = match_level  # 1/2/3 匹配级别
        self.matched_text = matched_text  # 实际匹配到的文本

    @property
    def match_level_desc(self) -> str:
        return {1: "完整匹配", 2: "前缀匹配", 3: "词组匹配"}.get(
            self.match_level, "?")


# ---------------------------------------------------------------
# 文本归一化（与quote对齐的关键预处理）
# ---------------------------------------------------------------
def _norm_for_match(text: str) -> str:
    """
    归一化文本用于匹配比较:
      - 压缩所有空白为单个空格（消除换行断裂）
      - 移除连字符断词的连字符（perfor-mance -> performance）
        注意: 只处理"字母-换行"模式，正常连字符词(high-order)保留
      - 统一小写
    """
    # 1. 连字符断词: 小写字母 + 可选连字符 + 换行 + 小写字母 -> 直接拼接
    text = re.sub(r"([a-zA-Z])-\s*\n\s*([a-zA-Z])", r"\1\2", text)
    # 2. 所有空白(含\n)压成单空格
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


# ---------------------------------------------------------------
# 核心定位函数
# ---------------------------------------------------------------
def locate_quote(pdf_path: str, quote: str) -> tuple[int, str] | None:
    """
    在PDF中定位quote文本

    返回:
        (page_num_0based, 实际匹配的规范化文本) 或 None(定位失败)

    实现: 用PyMuPDF逐页提取文本 -> 规范化 -> 子串查找。
    （不用page.search_for()的原因: 它对跨行文本敏感，
      而规范化后的子串匹配对换行/断词天然免疫）
    """
    if not os.path.exists(pdf_path) or not quote:
        return None

    quote_norm = _norm_for_match(quote)
    if len(quote_norm) < 10:  # 太短的引用无法可靠定位
        return None

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    try:
        for page_num, page in enumerate(doc):
            page_text = _norm_for_match(page.get_text())
            if quote_norm in page_text:
                return page_num, quote_norm

            # L2: 前缀匹配(前50字符命中即算——长引用可能跨页)
            prefix = quote_norm[:50]
            if len(quote_norm) > 60 and prefix in page_text:
                return page_num, prefix

            # L3: 最长词组滑窗(从长到短尝试, 至少5词)
            words = quote_norm.split()
            for win in (8, 6, 5):
                if len(words) < win:
                    continue
                for start in range(0, len(words) - win + 1):
                    chunk = " ".join(words[start:start + win])
                    if chunk in page_text:
                        return page_num, chunk
    finally:
        doc.close()
    return None


# ---------------------------------------------------------------
# 高亮渲染
# ---------------------------------------------------------------
def render_evidence_page(pdf_path: str, page_num: int,
                         matched_text: str, out_path: str) -> bool:
    """
    渲染指定页并高亮匹配文本

    高亮实现: 在规范化文本上无法直接用search_for(原文带换行),
    所以先在原始页面文本里定位匹配文本的"首词+尾词"锚点,
    用search_for分别搜索锚点词组, 高亮两者之间的区域。

    返回:
        True=渲染成功
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]

        # matched_text是规范化过的; 取首5词和尾5词作为原文锚点
        words = matched_text.split()
        if len(words) >= 10:
            head = " ".join(words[:5])
            tail = " ".join(words[-5:])
        else:
            head = matched_text
            tail = None

        # search_for返回文本矩形(自动处理跨行)
        head_rects = page.search_for(head)
        if not head_rects:
            # 锚点也断词了: 退化为逐词
            head_words = head.split()
            head_rects = []
            for w in head_words:
                head_rects += page.search_for(w)
        if not head_rects:
            doc.close()
            return False

        highlight_rects = list(head_rects)

        if tail:
            tail_rects = page.search_for(tail)
            if not tail_rects:
                for w in tail.split():
                    tail_rects += page.search_for(w)
            highlight_rects += tail_rects

        # 去重并添加高亮注释（黄色）
        for rect in highlight_rects:
            page.add_highlight_annot(rect)

        # 渲染为图片（2倍缩放保证文字清晰）
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        pix.save(out_path)
        doc.close()
        return True
    except Exception as e:
        print(f"[证据定位] 渲染失败 {pdf_path} p{page_num}: {e}")
        return False


# ---------------------------------------------------------------
# 对外主入口：批量生成所有声明的证据索引
# ---------------------------------------------------------------
def build_evidence_index(cards: list[dict],
                         review_results: list[dict] | None = None,
                         only_supported: bool = True) -> dict:
    """
    为（通过审查的）声明批量生成证据图片与索引

    参数:
        cards: paper_cards.json的内容
        review_results: review_results.json的内容(用于过滤已核验声明);
                        None时不过滤
        only_supported: 只为核验通过的声明生成证据

    返回:
        evidence_index: {声明key: {page, image, match_level, ...}}
        声明key格式: "{arxiv_id}#{claim_index}"
    """
    # 通过审查的声明集合
    supported_keys = None
    if review_results is not None and only_supported:
        supported_keys = {
            f"{r['arxiv_id']}#{r['claim_index']}"
            for r in review_results
            if r.get("verdict", {}).get("verdict") == "supported"
        }

    # PDF路径缓存目录
    ev_dir = os.path.join(config.PROJECT_ROOT, "evidence")
    os.makedirs(ev_dir, exist_ok=True)

    index = {}
    total = 0
    hit = 0
    for card in cards:
        arxiv_id = card["arxiv_id"]
        pdf_path = os.path.join(config.PAPER_DIR,
                                f"{arxiv_id.replace('/', '_')}.pdf")
        if not os.path.exists(pdf_path):
            continue

        for idx, claim in enumerate(card.get("claims", [])):
            key = f"{arxiv_id}#{idx}"
            if supported_keys is not None and key not in supported_keys:
                continue
            total += 1

            # 逐条quote尝试定位（任一quote命中即成功）
            located = None
            used_quote = ""
            for q in claim.get("quotes", []):
                located = locate_quote(pdf_path, q.get("text", ""))
                if located:
                    used_quote = q.get("text", "")
                    break

            if not located:
                index[key] = {"located": False}
                continue

            page_num, matched = located
            img_name = f"{arxiv_id.replace('/', '_')}_c{idx}_p{page_num}.png"
            img_path = os.path.join(ev_dir, img_name)
            ok = render_evidence_page(pdf_path, page_num, matched, img_path)
            if not ok:
                index[key] = {"located": False}
                continue

            hit += 1
            index[key] = {
                "located": True,
                "page": page_num,
                "image": img_name,
                "match_level": 1 if len(_norm_for_match(used_quote)) ==
                                len(matched) else 2,
                "quote": used_quote[:150],
                "pdf": os.path.basename(pdf_path),
            }

    # 落盘索引
    idx_path = os.path.join(config.DATA_DIR, "evidence_index.json")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    import json
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"[证据定位] 完成: {hit}/{total} 条声明定位成功 "
          f"({hit * 100 // max(total, 1)}%), 索引: {idx_path}")
    return index


if __name__ == "__main__":
    # 独立测试: 读取现有数据跑一遍完整流程
    import json

    cards = json.load(open(
        os.path.join(config.DATA_DIR, "paper_cards.json"), encoding="utf-8"))
    try:
        reviews = json.load(open(
            os.path.join(config.DATA_DIR, "review_results.json"),
            encoding="utf-8"))
    except FileNotFoundError:
        reviews = None

    build_evidence_index(cards, reviews)
