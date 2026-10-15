# -*- coding: utf-8 -*-
"""
make_opening_ppt.py —— 生成开题答辩PPT
================================
基于 literature_agent 项目四周来的真实实验数据，
按开题答辩要求组织四大板块:
  1 待解决的问题(问题发现)  2 现状调研
  3 贡献点/创新点说明        4 可行性分析(先导实验)

运行: conda activate brain && python make_opening_ppt.py
输出: output/开题答辩.pptx
"""
import os

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

# ---- 视觉系统(与Streamlit前端同一套靛紫渐变观感) ----
PRIMARY = RGBColor(0x4F, 0x46, 0xE5)   # 靛蓝主色
ACCENT = RGBColor(0x7C, 0x3A, 0xED)    # 紫罗兰强调
TEXT = RGBColor(0x0F, 0x17, 0x2A)      # 正文深色
GRAY = RGBColor(0x47, 0x55, 0x69)      # 次级灰
LIGHT = RGBColor(0xF8, 0xFA, 0xFC)     # 浅底
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x05, 0x96, 0x69)     # 实测数据绿
RED = RGBColor(0xDC, 0x26, 0x26)       # 痛点红
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


# ---------------------------------------------------------------
# 基础工具函数
# ---------------------------------------------------------------
def _ea(run, name=FONT):
    """设置东亚字体(中文需额外写a:ea节点, 否则中文回退宋体)"""
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", name)


def add_rect(slide, x, y, w, h, color, radius=False):
    """纯色矩形(卡片底/标题条)"""
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def add_text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP):
    """
    多行文本块. lines: [(text, size, bold, color, bullet前缀已含), ...]
    元组第5位可选(行距倍数)
    """
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, spec in enumerate(lines):
        text, size, bold, color = spec[0], spec[1], spec[2], spec[3]
        spacing = spec[4] if len(spec) > 4 else 1.0
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(4)
        if spacing != 1.0:
            p.line_spacing = spacing
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = FONT
        _ea(run)
    return tb


def page_base(title, section=None, num=None):
    """内容页骨架: 顶部渐变标题条 + 左侧色条 + 页脚(页码自动编号)"""
    slide = prs.slides.add_slide(BLANK)
    _PAGE_NO[0] += 1  # 封面占第1页, 此后每调用一次自动+1
    add_rect(slide, 0, 0, prs.slide_width, Emu(1), LIGHT)  # 底色
    bg = add_rect(slide, Inches(0), Inches(0), prs.slide_width,
                  prs.slide_height, LIGHT)
    bg.shadow.inherit = False
    # 左侧竖色条
    add_rect(slide, Inches(0.45), Inches(0.42), Inches(0.09),
             Inches(0.62), PRIMARY)
    # 章节小标
    if section:
        add_text(slide, Inches(0.62), Inches(0.18), Inches(6),
                 Inches(0.35), [(section, 12, True, ACCENT)])
    # 页标题
    add_text(slide, Inches(0.62), Inches(0.46), Inches(11.5),
             Inches(0.7), [(title, 27, True, TEXT)])
    # 页脚（自动页码, num参数保留仅为兼容旧调用）
    add_text(slide, Inches(12.1), Inches(7.05), Inches(1),
             Inches(0.3), [(str(_PAGE_NO[0]), 11, False, GRAY)],
             align=PP_ALIGN.RIGHT)
    return slide

_PAGE_NO = [1]  # 页码计数器(封面=1), 定义在函数后也可用(运行时查找)


def make_table(slide, x, y, w, rows_data, col_widths, header_fill=PRIMARY,
               font_size=12, row_h=0.42):
    """数据表: 首行为主色表头白字, 数据行斑马纹"""
    n_rows, n_cols = len(rows_data), len(rows_data[0])
    shape = slide.shapes.add_table(n_rows, n_cols, x, y, w,
                                   Inches(row_h * n_rows))
    table = shape.table
    for c, cw in enumerate(col_widths):
        table.columns[c].width = Inches(cw)
    for r, row in enumerate(rows_data):
        table.rows[r].height = Inches(row_h)
        for c, val in enumerate(row):
            cell = table.cell(r, c)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if c > 0 or r == 0 else PP_ALIGN.LEFT
            run = p.add_run()
            run.text = str(val)
            run.font.name = FONT
            _ea(run)
            if r == 0:                       # 表头
                run.font.size = Pt(font_size)
                run.font.bold = True
                run.font.color.rgb = WHITE
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_fill
            else:                            # 数据行
                run.font.size = Pt(font_size)
                run.font.bold = (c == 0)
                run.font.color.rgb = TEXT
                cell.fill.solid()
                cell.fill.fore_color.rgb = (WHITE if r % 2
                                            else RGBColor(0xEE, 0xF2, 0xFF))
    return table


def card(slide, x, y, w, h, title, body_lines, tcolor=PRIMARY):
    """圆角卡片: 标题+正文"""
    add_rect(slide, x, y, w, h, WHITE, radius=True)
    add_text(slide, x + Inches(0.18), y + Inches(0.12), w - Inches(0.36),
             Inches(0.4), [(title, 15, True, tcolor)])
    specs = [(t, s, b, c) for (t, s, b, c) in body_lines]
    add_text(slide, x + Inches(0.18), y + Inches(0.55), w - Inches(0.36),
             h - Inches(0.7), specs)


# ================================================================
# 第1页 封面
# ================================================================
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, prs.slide_width, prs.slide_height, PRIMARY)
add_rect(s, Inches(0), Inches(4.9), prs.slide_width, Inches(0.06), WHITE)
add_text(s, Inches(1), Inches(2.0), Inches(11.3), Inches(1.8), [
    ("基于多智能体协作与证据约束的", 38, True, WHITE, 1.15),
    ("可信科研文献综述生成系统", 38, True, WHITE, 1.15),
], align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(4.0), Inches(11.3), Inches(0.5),
         [("—— 检索、核验、拒答、工程可靠性的一体化设计与先导实验 ——",
           16, False, RGBColor(0xC7, 0xD2, 0xFE))], align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(5.2), Inches(11.3), Inches(1.2), [
    ("开题答辩（第1—4周）", 17, True, WHITE, 1.5),
    ("汇报人：XXX      指导教师：XXX      2026 年 9 月",
     14, False, RGBColor(0xC7, 0xD2, 0xFE)),
], align=PP_ALIGN.CENTER)

# ================================================================
# 第2页 汇报提纲
# ================================================================
s = page_base("汇报提纲", num=2)
items = [
    ("00  选题依据", "价值导向 / 可行性 / 创新性 —— 三维度校验"),
    ("01  待解决的问题（问题发现）", "人工综述之痛 / 关键词漏检实证 / LLM幻觉 / API限流实测"),
    ("02  现状调研", "主流工具横向对比 / 技术路线缺口分析"),
    ("03  贡献点与创新点", "证据约束问答 / 引用链经典召回 / 检索可靠性工程"),
    ("04  可行性分析（先导实验）", "端到端实测/性能加速(已完成) + 核验·召回·成本实验(进行中) + 风险对策"),
]
for i, (t, d) in enumerate(items):
    y = Inches(1.32 + i * 1.13)
    add_rect(s, Inches(1.0), y, Inches(11.3), Inches(0.98), WHITE,
             radius=True)
    add_text(s, Inches(1.3), y + Inches(0.08), Inches(10.6), Inches(0.85),
             [(t, 17.5, True, PRIMARY), (d, 12.5, False, GRAY)])

# ================================================================
# 第3页 板块零: 选题依据——三维度校验(对应课程"如何选题"框架)
# ================================================================
s = page_base("选题依据：价值 / 可行 / 创新 三维度校验", "00 选题依据", num=3)
dims = [
    ("价值导向 · 解决真问题", [
        ("真实需求: 综述调研人工耗时数天,", 12.5, False, TEXT),
        ("四大痛点均有实测数据支撑(非假设)", 12.5, False, TEXT),
        ("产业前沿: LLM多智能体+证据约束问答,", 12.5, False, TEXT),
        ("直击生成式AI的幻觉痛点", 12.5, False, TEXT),
        ("可展示/可评估: 双主题端到端现场演示,", 12.5, False, TEXT),
        ("六项量化指标可复现供质询", 12.5, False, TEXT)]),
    ("可行性 · 先确保做得出来", [
        ("能力匹配: 检索/爬虫/SQLite/Streamlit", 12.5, False, TEXT),
        ("均为已掌握技术栈, 无模型训练需求", 12.5, False, TEXT),
        ("数据可获取: arXiv/OpenAlex/S2公开API", 12.5, False, TEXT),
        ("算力可支撑: 仅调LLM API, CPU即可运行", 12.5, False, TEXT),
        ("周期可控: 核心链路开题4周内已跑通,", 12.5, False, TEXT),
        ("为12周总周期留足迭代余量", 12.5, False, TEXT)]),
    ("创新性 · 再追求做得新", [
        ("方法创新: 程序化对齐+语义复检两级核验,", 12.5, False, TEXT),
        ("声明级溯源+结构化拒答", 12.5, False, TEXT),
        ("融合创新: 引用链挖掘×多Agent协作×", 12.5, False, TEXT),
        ("可靠性工程, 构成缺一不可的闭环", 12.5, False, TEXT),
        ("体验创新: 每句回答可回溯PDF逐字原文,", 12.5, False, TEXT),
        ("拒答机制本身即差异化卖点", 12.5, False, TEXT)]),
]
for i, (t, b) in enumerate(dims):
    card(s, Inches(0.55 + i * 4.15), Inches(1.5), Inches(3.95), Inches(3.65),
         t, b)
add_rect(s, Inches(0.55), Inches(5.45), Inches(12.2), Inches(1.2), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(5.6), Inches(11.6), Inches(1.0), [
    ("选题路径校验: 从痛点出发(板块①) → 快速验证(先导实验端到端已跑通) → 找到创新点(板块③);",
     13, False, TEXT, 1.3),
    ("三个维度缺一不可 —— 先确保障做得出来, 再追求做得新, 最终做得有价值。",
     13, True, ACCENT, 1.3),
])

# ================================================================
# 第3页 板块一: 待解决的问题——痛点
# ================================================================
s = page_base("待解决的问题：四大痛点（问题发现）", "① 问题发现", num=3)
pain = [
    ("痛点1 · 文献综述耗时", [
        ("一篇综述需人工跨库检索并精读数十篇论文", 12.5, False, TEXT),
        ("检索→筛选→下载→精读→撰写全流程手工", 12.5, False, TEXT),
        ("高质量信号(被引/共被引/出处)分散在多个平台", 12.5, False, GRAY),
    ], RED),
    ("痛点2 · 关键词漏检奠基论文（实证）", [
        ("实证: SpikeProp(2000)摘要早于现代术语, 缺", 12.5, False, TEXT),
        ("'surrogate gradient'等词 → 关键词检索漏检", 12.5, False, TEXT),
        ("结论: 引用链挖掘是标准补救通道", 12.5, True, ACCENT),
    ], RED),
    ("痛点3 · LLM幻觉, 生成内容无法溯源", [
        ("通用问答无法区分\"文献证据\"与\"模型编造\"", 12.5, False, TEXT),
        ("学术场景下引用错页码/错作者风险高", 12.5, False, TEXT),
        ("缺乏\"证据不足时拒答\"机制", 12.5, False, GRAY),
    ], RED),
    ("痛点4 · 免费学术API限流严重（实测）", [
        ("OpenAlex免费档$0.1/天≈100次请求", 12.5, False, TEXT),
        ("S2匿名模式频繁429; arXiv API间歇封锁", 12.5, False, TEXT),
        ("实测: 单主题运行85次元数据请求即烧穿额度", 12.5, True, ACCENT),
    ], RED),
]
for i, (t, b, c) in enumerate(pain):
    card(s, Inches(0.55 + (i % 2) * 6.35), Inches(1.45 + (i // 2) * 2.75),
         Inches(6.15), Inches(2.55), t, b, tcolor=c)

# ================================================================
# 第4页 板块一: 问题聚焦
# ================================================================
s = page_base("问题聚焦：核心研究问题", "① 问题发现", num=4)
add_rect(s, Inches(0.9), Inches(1.5), Inches(11.5), Inches(1.5), WHITE,
         radius=True)
add_text(s, Inches(1.2), Inches(1.72), Inches(11), Inches(1.1), [
    ("如何构建一个让 LLM 在文献综述任务中", 18, True, PRIMARY, 1.3),
    ("\"有据可查、不足可拒、经典不漏、稳定可用\" 的自动化系统？",
     18, True, PRIMARY),
])
subs = [
    ("子问题A · 可信性", [
        ("每条结论都能回溯到PDF原文逐字引用;", 13, False, TEXT),
        ("证据不足时结构化拒答而非编造", 13, False, TEXT)]),
    ("子问题B · 召回性", [
        ("关键词检索 + 引用链挖掘 + LLM领域先验", 13, False, TEXT),
        ("三路互补, 奠基论文不因术语演化而漏检", 13, False, TEXT)]),
    ("子问题C · 稳定性", [
        ("限流/配额/单点故障下的持续服务能力,", 13, False, TEXT),
        ("缓存复用与多源自动降级", 13, False, TEXT)]),
]
for i, (t, b) in enumerate(subs):
    card(s, Inches(0.9 + i * 3.95), Inches(3.45), Inches(3.7), Inches(2.2),
         t, b)

# ================================================================
# 第5页 板块二: 现状调研——工具对比
# ================================================================
s = page_base("现状调研：主流工具横向对比", "② 现状调研", num=5)
rows = [
    ["能力维度", "ChatGPT等通用LLM", "Consensus", "Elicit", "本系统"],
    ["证据逐字溯源到原文", "✗ 引用常凭印象, 可能编造", "△ 引用锚定原句(2026新)", "△ 句子级引用+引句支撑", "✓ PDF逐字对齐+双重核验"],
    ["证据不足时拒答", "✗ 照常生成", "△ 有证据强度提示仍作答", "✗ 无明确拒答", "✓ 结构化拒答(声明池约束)"],
    ["奠基论文召回(引用链)", "✗", "△ 部分有", "△ 部分有", "✓ 共被引挖掘+LLM先验注入"],
    ["限流/配额应对", "—", "—", "—", "✓ 缓存+熔断+四级降级(实测)"],
    ["结果可复现性", "✗ 温度随机", "△", "△", "✓ 温度0.1+落盘证据库"],
    ["本地化部署/费用可控", "—", "✗ 闭源SaaS", "✗ 闭源SaaS", "✓ 全开源栈本地运行"],
]
make_table(s, Inches(0.55), Inches(1.5), Inches(12.2), rows,
           [2.5, 2.4, 1.9, 1.9, 3.5], font_size=12, row_h=0.62)
add_text(s, Inches(0.55), Inches(6.3), Inches(12), Inches(0.5),
         [("调研方法: 逐工具实测(同主题\"脉冲神经网络高效训练方法\") + 官方文档比对, 2026-09 完成",
           11.5, False, GRAY)])

# ================================================================
# 第6页 板块二: 技术路线与缺口
# ================================================================
s = page_base("现状调研：相关技术路线与缺口", "② 现状调研", num=6)
routes = [
    ("RAG 检索增强生成", [
        ("面向开放语料的\"边检边答\";", 12.5, False, TEXT),
        ("缺少\"先核验后生成\"的两级质检,", 12.5, False, TEXT),
        ("无法保证每句可溯源", 12.5, False, GRAY)]),
    ("引用链滚雪球 Snowballing", [
        ("系统性综述的标准召回手段;", 12.5, False, TEXT),
        ("现有工具少有工程化落地,", 12.5, False, TEXT),
        ("且依赖单一数据源(易缺参考文献)", 12.5, False, GRAY)]),
    ("多智能体 LLM 编排", [
        ("任务分工提升稳定性;", 12.5, False, TEXT),
        ("但学术工具普遍缺少:", 12.5, False, TEXT),
        ("Agent间结构化证据契约与审计", 12.5, False, GRAY)]),
]
for i, (t, b) in enumerate(routes):
    card(s, Inches(0.55 + i * 4.15), Inches(1.5), Inches(3.95), Inches(2.6),
         t, b)
add_rect(s, Inches(0.55), Inches(4.4), Inches(12.2), Inches(1.9), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(4.6), Inches(11.7), Inches(1.6), [
    ("研究缺口（本课题切入点）", 16, True, ACCENT),
    ("现有方案没有同时做到:  ①声明级核验与拒答  ②经典论文多通道召回  ③免费API下的工程可靠性。",
     13.5, False, TEXT, 1.35),
    ("三者恰是\"可信文献综述自动化\"缺一不可的闭环 —— 本系统以结构化证据库(JSON/SQLite)为中枢串联全部Agent。",
     13.5, False, TEXT, 1.35),
])

# ================================================================
# 第7页 板块三: 系统架构与创新点总览
# ================================================================
s = page_base("贡献点总览：系统架构与三大创新", "③ 创新点", num=7)
# 架构流水线
agents = ["规划Agent", "检索Agent", "下载Agent", "提取Agent", "审查Agent",
          "综合Agent"]
ax = Inches(0.55)
for i, name in enumerate(agents):
    x = Emu(int(ax) + i * Emu(int(Inches(1.62))))
    add_rect(s, x, Inches(1.5), Inches(1.5), Inches(0.62), PRIMARY,
             radius=True)
    add_text(s, x, Inches(1.58), Inches(1.5), Inches(0.5),
             [(name, 13, True, WHITE)], align=PP_ALIGN.CENTER)
    if i < 5:
        add_text(s, Emu(int(x) + int(Inches(1.5))), Inches(1.55),
                 Inches(0.14), Inches(0.5), [("→", 14, True, GRAY)],
                 align=PP_ALIGN.CENTER)
add_text(s, Inches(0.55), Inches(2.18), Inches(12), Inches(0.4),
         [("证据中枢: papers_meta.json(元数据) / paper_cards.json(信息卡片+逐字引用) / review_results.json(核验结论) / SQLite(缓存+请求日志)",
           12, False, GRAY)])
inno = [
    ("创新点1 · 证据约束问答与两级核验", [
        ("审查Agent两步走: 程序化引文对齐(全文子串匹配)", 12.5, False, TEXT),
        ("+ LLM语义一致性复检; 仅supported声明进入", 12.5, False, TEXT),
        ("问答池; 证据不足→结构化拒答(说明缺什么)", 12.5, False, TEXT),
        ("拒答能力本身即对幻觉的克制", 12.5, True, ACCENT)]),
    ("创新点2 · 三路互补的经典论文召回", [
        ("关键词检索 + 引用链共被引挖掘(≥3免LLM筛)", 12.5, False, TEXT),
        ("+ LLM领域先验注入(0.85相似度门限防错配)", 12.5, False, TEXT),
        ("S2兜底打通OpenAlex数据黑洞(~75%覆盖)", 12.5, False, TEXT),
        ("四路信号融合: 0.45相关+0.20RRF+0.15影响+0.20链", 12.5, True, ACCENT)]),
    ("创新点3 · 免费额度下的检索可靠性工程", [
        ("SQLite缓存(指纹键/7天TTL/只存200) + 双熔断器", 12.5, False, TEXT),
        ("四级数据源自动降级 S2→OA→Crossref→arXiv", 12.5, False, TEXT),
        ("救援双通道: API与PDF主机分离的关键洞察", 12.5, False, TEXT),
        ("全部实测量化(见先导实验)", 12.5, True, ACCENT)]),
]
for i, (t, b) in enumerate(inno):
    card(s, Inches(0.55 + i * 4.15), Inches(2.75), Inches(3.95),
         Inches(3.3), t, b)

# ================================================================
# 第8页 板块三: 创新点1详细
# ================================================================
s = page_base("创新点1：证据约束问答（Evidence-Bounded QA）", "③ 创新点", num=8)
steps = [
    ("Step1 声明抽取", "提取Agent从PDF全文抽取结构化声明\n每条附逐字原文引用(quote)"),
    ("Step2 程序化对齐", "代码验证quote确为PDF子串\n杜绝\"引用不存在的话\""),
    ("Step3 语义复检", "LLM判定声明与原文语义一致\n低温度(0.1)保证判定稳定"),
    ("Step4 声明池问答", "仅supported声明可被引用[声明#N]\n证据不足→结构化拒答"),
]
for i, (t, b) in enumerate(steps):
    x = Inches(0.55 + i * 3.18)
    add_rect(s, x, Inches(1.55), Inches(2.95), Inches(1.75), WHITE,
             radius=True)
    body = [(l, 12, False, TEXT, 1.25) for l in b.split("\n")]
    add_text(s, x + Inches(0.15), Inches(1.68), Inches(2.65), Inches(1.5),
             [(t, 14.5, True, PRIMARY), *body])
    if i < 3:
        add_text(s, Emu(int(x) + int(Inches(2.95))), Inches(2.1),
                 Inches(0.25), Inches(0.5), [("→", 16, True, GRAY)],
                 align=PP_ALIGN.CENTER)
add_rect(s, Inches(0.55), Inches(3.7), Inches(12.2), Inches(2.5), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(3.9), Inches(11.6), Inches(2.2), [
    ("与普通RAG问答的本质区别", 15.5, True, ACCENT),
    ("① 知识库边界: 只承认\"两级核验通过\"的声明, 检索噪声无法直接污染回答;", 13, False, TEXT, 1.3),
    ("② 每句可审计: 回答标注[声明#N], 可回溯到 paper_cards.json 的逐字引用与PDF页码;", 13, False, TEXT, 1.3),
    ("③ 拒答即卖点: 证据不足时输出\"缺什么类型的证据才能回答\", 证明系统对幻觉的克制(实测QA场景可复现)。",
     13, False, TEXT, 1.3),
])

# ================================================================
# 第9页 板块三: 创新点2详细
# ================================================================
s = page_base("创新点2：经典论文的三路互补召回", "③ 创新点", num=9)
lanes = [
    ("路1 关键词检索", [
        ("S2/OpenAlex双路并行+RRF融合", 12.5, False, TEXT),
        ("擅长新论文, 漏旧经典(痛点2)", 12.5, False, GRAY)]),
    ("路2 引用链共被引挖掘", [
        ("种子论文→参考文献→共被引≥3免LLM筛", 12.5, False, TEXT),
        ("OpenAlex缺数据时S2兜底(MAG直转", 12.5, False, TEXT),
        ("+arXiv DOI批量映射, 覆盖~75%)", 12.5, False, GRAY)]),
    ("路3 LLM领域先验注入", [
        ("规划Agent输出classic_titles清单", 12.5, False, TEXT),
        ("标题检索验证+0.85相似度门限", 12.5, False, TEXT),
        ("被引≥300才可豁免粗筛", 12.5, False, GRAY)]),
]
for i, (t, b) in enumerate(lanes):
    card(s, Inches(0.55 + i * 4.15), Inches(1.5), Inches(3.95),
         Inches(2.5), t, b)
rows = [
    ["实测案例(ChatGPT主题, 2026-09)", "修复前", "修复后"],
    ["HuggingGPT等12种子 → 共被引经典", "0 篇(整段空转)", "9 篇(InstructGPT/GPT-3/CoT)"],
    ["AlphaGo(Mastering the Game of Go)", "无法召回", "进入最终15篇候选"],
    ["Attention Is All You Need / BERT", "依赖LLM先验", "免检通道直入(chain_hits=3)"],
]
make_table(s, Inches(0.55), Inches(4.35), Inches(12.2), rows,
           [5.2, 3.2, 3.8], header_fill=ACCENT, font_size=12.5, row_h=0.5)

# ================================================================
# 第10页 板块三: 创新点3详细
# ================================================================
s = page_base("创新点3：免费额度下的检索可靠性工程", "③ 创新点", num=10)
mech = [
    ("缓存层 SQLite", [
        ("请求指纹键(SHA1, 参数排序无关)+7天TTL", 12.5, False, TEXT),
        ("只缓存HTTP 200(错误响应不入库)", 12.5, False, TEXT),
        ("命中打印提示, 与额度熔断解耦", 12.5, False, GRAY)]),
    ("双熔断器", [
        ("S2: 连续3次429→熔断5分钟自动恢复", 12.5, False, TEXT),
        ("OpenAlex: 累计6次429→熔断(与\"额度耗尽\"", 12.5, False, TEXT),
        ("永久熔断分离, 风暴可自愈)", 12.5, False, GRAY)]),
    ("四级降级链", [
        ("S2(认证)→OpenAlex→Crossref(免key)", 12.5, False, TEXT),
        ("→arXiv; 任一级失败滑向下一级,", 12.5, False, TEXT),
        ("流水线不断粮", 12.5, False, GRAY)]),
    ("救援双通道", [
        ("洞察: export.arxiv.org(API)与arxiv.org(PDF)", 12.5, False, TEXT),
        ("是不同主机——API故障时经S2反查编号", 12.5, False, TEXT),
        ("仍可从arxiv.org下载PDF", 12.5, False, GRAY)]),
]
for i, (t, b) in enumerate(mech):
    card(s, Inches(0.55 + (i % 2) * 6.35), Inches(1.5 + (i // 2) * 2.65),
         Inches(6.15), Inches(2.45), t, b)

# ================================================================
# 第11页 板块四: 先导实验1——端到端
# ================================================================
s = page_base("先导实验①：端到端流水线真实运行", "④ 可行性分析", num=11)
rows = [
    ["实测运行(2026-09, 真实网络)", "SNN主题", "ChatGPT主题"],
    ["候选论文(多源去重后)", "57 篇 / 10路RRF融合", "82 篇 / 7路RRF融合"],
    ["LLM粗筛后", "26 篇(含免检通道)", "37 篇(含2篇经典免检)"],
    ["PDF下载", "7/10(含救援)", "28/30(自适应前)→策略优化"],
    ["最终交付", "5篇卡片×4声明+综述+问答", "15篇卡片+逐字引用核验"],
    ["单篇提取声明数", "4 条 / 4 条逐字引用", "4 条 / 4 条逐字引用"],
]
make_table(s, Inches(0.55), Inches(1.5), Inches(12.2), rows,
           [3.7, 4.25, 4.25], font_size=12.5, row_h=0.52)
add_rect(s, Inches(0.55), Inches(5.0), Inches(12.2), Inches(1.35), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(5.15), Inches(11.6), Inches(1.1), [
    ("结论: 从\"一句话主题\"到\"可溯源的综述+可信问答\"全链路已跑通, 覆盖两类差异极大的主题(小众SNN / 爆炸增长LLM),",
     13, False, TEXT, 1.3),
    ("且审查Agent两级核验、QA拒答、引用图谱、报告生成均产出真实可用结果 —— 系统级可行性成立。",
     13, False, TEXT, 1.3),
])

# ================================================================
# 第12页 板块四: 先导实验2——性能实测
# ================================================================
s = page_base("先导实验②：可靠性工程性能实测", "④ 可行性分析", num=12)
rows = [
    ["指标", "优化前", "优化后", "加速/收益"],
    ["S2单请求耗时(撞429重试)", "22,199 ms", "13.4 ms(缓存命中)", "≈1650×"],
    ["OpenAlex单请求", "1,137 ms", "8.6 ms(缓存命中)", "≈132×"],
    ["同参数二次运行缓存命中率", "0%(无缓存层)", "67%", "元数据近零请求"],
    ["S2风暴期最坏等待(4关键词)", "≈4 分钟(10/20/30s退避)", "≈11 秒后熔断短路", "95%↓"],
    ["下载量(30候选/目标15)", "一次性30篇", "首批19篇按需补位", "省11篇≈17MB"],
    ["OpenAlex 400错误(逗号标题)", "每次必现", "0次(A/B实测语义不变)", "召回修复"],
]
make_table(s, Inches(0.55), Inches(1.5), Inches(12.2), rows,
           [3.5, 3.3, 3.3, 2.1], font_size=12.5, row_h=0.56)
add_text(s, Inches(0.55), Inches(5.6), Inches(12), Inches(1.2), [
    ("方法说明: A/B对照(mock模拟故障) + 请求日志表(req_log)逐条统计, 全部数据可由 cache.diag_summary() 复现;",
     12.5, False, GRAY, 1.35),
    ("实验环境: Windows 11 / Python 3.11 / 校园网环境, API均为免费公开额度。", 12.5, False, GRAY, 1.35),
])

# ================================================================
# 第13页 板块四: 先导实验3-5(核验/召回/成本)
# ================================================================
s = page_base("先导实验③④⑤：创新点的量化验证（第3—4周执行）", "④ 可行性分析", num=13)
trio = [
    ("实验③ 核验有效性（支撑创新点1）", [
        ("设计: 构造30条\"污染声明\"(改数字/换作者/", 12.5, False, TEXT),
        ("张冠李戴各10条)混入30条真实声明", 12.5, False, TEXT),
        ("指标: 错误拦截率≥90%, 误杀率<5%;", 12.5, False, TEXT),
        ("另测10个超纲问题, 统计实际拒答率", 12.5, False, TEXT),
        ("状态: 进行中(与队友审查基准测试协同)", 12.5, True, ACCENT)]),
    ("实验④ 召回率对照（支撑创新点2）", [
        ("设计: 3个领域×10篇公认奠基论文作标准答案", 12.5, False, TEXT),
        ("对照: 纯关键词检索 vs 三路互补召回", 12.5, False, TEXT),
        ("预期: 关键词≈50-60%, 三路≥90%", 12.5, False, TEXT),
        ("已有线索: SpikeProp个案实测漏检,", 12.5, False, TEXT),
        ("本实验把个案变成系统性数字", 12.5, True, ACCENT)]),
    ("实验⑤ 成本核算（支撑免费可行）", [
        ("设计: 统计单次全流程LLM token消耗", 12.5, False, TEXT),
        ("与数据源API调用次数", 12.5, False, TEXT),
        ("预期: 单次全流程<$0.1,", 12.5, False, TEXT),
        ("二次运行(缓存命中)≈$0", 12.5, False, TEXT),
        ("一句话结论: \"每个学生都用得起\"", 12.5, True, ACCENT)]),
]
for i, (t, b) in enumerate(trio):
    card(s, Inches(0.55 + i * 4.15), Inches(1.5), Inches(3.95), Inches(3.3),
         t, b)
add_rect(s, Inches(0.55), Inches(5.1), Inches(12.2), Inches(1.35), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(5.25), Inches(11.6), Inches(1.1), [
    ("先导实验矩阵（三层递进）", 14, True, PRIMARY),
    ("已完成: ①端到端跑通 ②性能加速 —— 证明\"做得出来、跑得快\";   进行中: ③核验有效性 ④召回率对照 —— 证明\"做得好\";",
     12.5, False, TEXT, 1.3),
    ("计划: ⑤成本核算 —— 证明\"用得起\"。可行性论证从\"能跑\"升级为\"能跑+好用+便宜\"的完整闭环。",
     12.5, True, ACCENT, 1.3),
])

# ================================================================
# 第14页 板块四: 风险对策与4周计划
# ================================================================
s = page_base("可行性分析：风险对策与 4 周执行计划", "④ 可行性分析", num=13)
rows = [
    ["风险", "对策", "状态"],
    ["OpenAlex $0.1/天额度烧穿", "缓存复用+Crossref第二主源分摊", "✅ 已实测"],
    ["S2/OpenAlex 429风暴", "熔断器+退避优化+四级降级链", "✅ 已实测"],
    ["出版社PDF反爬(403)", "限定arXiv来源+标题救援双通道", "✅ 已实测"],
    ["OpenAlex引用数据黑洞", "S2兜底+LLM先验注入", "✅ 已实测"],
    ["长论文提取丢信息", "截断上限60K→100K字符", "✅ 已实施"],
]
make_table(s, Inches(0.55), Inches(1.45), Inches(6.6), rows,
           [2.6, 3.1, 0.9], font_size=11.5, row_h=0.48)
plan = [
    ("第1周 ✅", "检索缓存层(指纹键/TTL/请求日志)"),
    ("第2周 ✅", "Crossref第二主源+引用链S2兜底"),
    ("第3周 ▶", "断点续跑+实验③核验拦截率/④召回率对照"),
    ("第4周", "实验⑤成本核算+诊断面板+开题报告整理"),
]
add_text(s, Inches(7.6), Inches(1.5), Inches(5.2), Inches(0.4),
         [("4周开题期计划(=12周总周期前1/3, 核心功能已超前跑通)", 14, True, PRIMARY)])
for i, (w, d) in enumerate(plan):
    y = Inches(2.0 + i * 0.72)
    add_rect(s, Inches(7.6), y, Inches(5.2), Inches(0.6), WHITE,
             radius=True)
    add_text(s, Inches(7.8), y + Inches(0.08), Inches(4.9), Inches(0.5),
             [(f"{w}   {d}", 12.5, False, TEXT)])
add_rect(s, Inches(7.6), Inches(5.0), Inches(5.2), Inches(1.5), WHITE,
         radius=True)
add_text(s, Inches(7.85), Inches(5.15), Inches(4.7), Inches(1.3), [
    ("技术可行性: 全开源栈", 14, True, ACCENT),
    ("PyMuPDF / requests / SQLite / Streamlit / DeepSeek API(低温0.1)", 12,
     False, TEXT, 1.3),
    ("无训练需求, CPU即可运行", 12, False, GRAY, 1.3),
])

# ================================================================
# 第14页 AI声明+总结
# ================================================================
s = page_base("总结与声明", num=14)
add_rect(s, Inches(0.55), Inches(1.4), Inches(12.2), Inches(2.0), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(1.55), Inches(11.6), Inches(1.7), [
    ("总结", 16, True, PRIMARY),
    ("围绕\"可信文献综述自动化\", 完成问题发现(四大痛点含实证)、现状调研(六维对比)、三大创新点设计与先导实验:",
     13, False, TEXT, 1.3),
    ("端到端双主题跑通 + 可靠性工程六项指标量化(最高≈1650×加速)。检索/核验/拒答闭环可行性已由真实数据支撑。",
     13, False, TEXT, 1.3),
])
add_rect(s, Inches(0.55), Inches(3.7), Inches(12.2), Inches(2.5), WHITE,
         radius=True)
add_text(s, Inches(0.85), Inches(3.85), Inches(11.6), Inches(2.2), [
    ("AI 工具使用声明（学术规范）", 16, True, ACCENT),
    ("① AI辅助范围: 代码实现(chatgpt/claude辅助编码)、文献数据源API调研、PPT排版生成;", 13, False, TEXT, 1.3),
    ("② 人工验证: 全部性能数据来自本人设计并执行的A/B对照实验与请求日志审计, 关键结论(如85×加速/75%映射覆盖)经复跑验证;",
     13, False, TEXT, 1.3),
    ("③ 实验可复现: 代码、缓存库与请求日志均本地留存, diag_summary()可一键输出诊断报告供答辩质询;",
     13, False, TEXT, 1.3),
    ("④ 系统内LLM生成内容一律经两级核验并标注来源, 未核验内容不进入最终报告。", 13, False, TEXT, 1.3),
])
add_text(s, Inches(0.55), Inches(6.6), Inches(12.2), Inches(0.6),
         [("恳请各位老师批评指正！", 20, True, PRIMARY)],
         align=PP_ALIGN.CENTER)

# ---- 保存 ----
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, "开题答辩.pptx")
prs.save(out)
print(f"已生成: {out}  共{len(prs.slides.__iter__.__self__._sldIdLst)}页")
