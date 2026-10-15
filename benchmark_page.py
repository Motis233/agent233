# -*- coding: utf-8 -*-
"""
benchmark_page.py —— 实验③"拦错结论测试"结果展示页(供答辩截图)
==============================================================
读取 data/benchmark_review.json, 展示:
  实验设计 → 核心指标(拦截率/误伤率/拒答正确率) → 逐条明细 → 典型案例
运行: conda run -n brain streamlit run benchmark_page.py --server.port 8502
访问: http://127.0.0.1:8502
"""
import json
import os

import streamlit as st

st.set_page_config(page_title="实验③ · 拦错结论测试", page_icon="🧪",
                   layout="wide")

# ---- 视觉: 与主应用一致的靛紫风格 ----
st.markdown("""
<style>
  .stApp { background: #F8FAFC; }
  h1 { color: #0F172A !important; }
  .metric-card { background:#fff; border:1px solid #E2E8F0;
                 border-radius:14px; padding:18px 20px; }
  .big-num { font-size:40px; font-weight:800; color:#4F46E5;
             line-height:1.1; }
  .big-num-good { color:#059669; }
  .sub { color:#475569; font-size:14px; margin-top:4px; }
  .pass-banner { background:#ECFDF5; border:1px solid #A7F3D0;
                 border-radius:12px; padding:14px 18px; font-size:17px;
                 color:#065F46; font-weight:600; }
  .fail-banner { background:#FEF2F2; border:1px solid #FECACA;
                 border-radius:12px; padding:14px 18px; font-size:17px;
                 color:#991B1B; font-weight:600; }
</style>
""", unsafe_allow_html=True)

st.title("🧪 实验③ · 拦错结论测试")
st.caption("验证对象: 设计一「让每句话都有出处」的两级核验模块 ｜ "
           "对应开题答辩第13页 先导实验③")


@st.cache_data(ttl=600)
def load_result():
    path = "data/benchmark_review.json"
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


data = load_result()
if data is None:
    st.warning("⏳ 实验正在运行中(60条声明逐条送审真实审查Agent, 约需几分钟)。"
               "完成后结果文件 data/benchmark_review.json 生成, 刷新本页即可。")
    st.stop()
meta, summary = data["meta"], data["summary"]
claims = data["claims"]
refusal = data.get("refusal", {})

# ---- 实验设计说明 ----
with st.container(border=True):
    st.markdown("##### 实验设计")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**30条真结论**\n\n来自真实跑通的论文信息卡片,"
                "每条都带真实原文引用")
    c2.markdown("**30条污染结论(LLM改错)**\n\n"
                "改数字 / 张冠李戴 / 夸大范围 三种攻击各10条,"
                "**保留真实引用** —— 引用是真的, 内容是错的")
    c3.markdown("**60条混排盲测**\n\n"
                "固定随机种子洗牌后, 全部送入真实审查Agent"
                "(程序对齐 + LLM语义复核), 无任何特殊照顾")

# ---- 核心指标 ----
m1, m2, m3, m4 = st.columns(4)
m1.markdown(f"""
<div class="metric-card"><div class="big-num">{meta['n_polluted'] + meta['n_real']}</div>
<div class="sub">送审声明总数(污染{meta['n_polluted']} + 真{meta['n_real']})</div></div>
""", unsafe_allow_html=True)
rate_pct = f"{summary['interception_rate']:.0%}"
m2.markdown(f"""
<div class="metric-card"><div class="big-num big-num-good">{rate_pct}</div>
<div class="sub">污染拦截率 {summary['polluted_caught']}/{meta['n_polluted']}
（通过线 ≥90%）</div></div>
""", unsafe_allow_html=True)
m3.markdown(f"""
<div class="metric-card"><div class="big-num">{summary['false_kill_rate']:.0%}</div>
<div class="sub">真结论误伤率 {summary['real_rejected']}/{meta['n_real']}（越低越好）</div></div>
""", unsafe_allow_html=True)
acc = refusal.get("overall")
acc_txt = f"{acc:.0%}" if isinstance(acc, (int, float)) else "—"
m4.markdown(f"""
<div class="metric-card"><div class="big-num">{acc_txt}</div>
<div class="sub">问答拒答测试正确率（可答+超纲混合）</div></div>
""", unsafe_allow_html=True)

# ---- 结论横幅 ----
if summary["passed"]:
    st.markdown(f"""
<div class="pass-banner">✅ 通过线达成：污染拦截率 {rate_pct} ≥ 90% ——
"每句话都有出处"的核验设计被证明真实有效，不是纸上方案。</div>
""", unsafe_allow_html=True)
else:
    st.markdown(f"""
<div class="fail-banner">⚠️ 未达通过线：拦截率 {rate_pct} &lt; 90% ——
需回看误放行的案例并调整核验阈值。</div>
""", unsafe_allow_html=True)

# ---- 逐条明细 ----
st.subheader("逐条核验明细")
view = st.radio("查看", ["全部", "仅污染结论", "仅真结论"], horizontal=True)
rows = claims
if view == "仅污染结论":
    rows = [c for c in claims if c["group"] == "polluted"]
elif view == "仅真结论":
    rows = [c for c in claims if c["group"] == "real"]

for i, c in enumerate(rows):
    if c["group"] == "polluted":
        icon = "🚫" if c["caught"] else "❌漏网"
        head = (f"{icon} [{c['attack']}] {c['content'][:60]}")
    else:
        icon = "✅" if not c["caught"] else "⚠️误伤"
        head = f"{icon} (真) {c['content'][:60]}"
    with st.expander(head):
        st.markdown(
            f"**论文**: {c['paper']} ｜ **程序对齐**: "
            f"{'通过' if c['aligned'] else '未通过'} ｜ "
            f"**语义判定**: `{c['verdict']}` ｜ 置信度 {c['confidence']}")
        st.write(f"**审查员理由**: {c['reason']}")
        if c["group"] == "polluted":
            st.info(f"**原始真结论** → {c['orig']}")

# ---- 拒答测试 ----
if refusal and "details" in refusal:
    st.subheader("附加 · 超纲问题拒答测试")
    st.caption("可答组(答案在证据库里)应正常回答; 拒答组(知识库外, 10题)应明确拒答")
    ra = refusal.get("refusal_acc")
    aa = refusal.get("answerable_acc")
    c1, c2 = st.columns(2)
    c1.metric("超纲组拒答正确率", f"{ra:.0%}" if isinstance(ra, (int, float)) else "—")
    c2.metric("可答组回答正确率", f"{aa:.0%}" if isinstance(aa, (int, float)) else "—")
    for d in refusal["details"]:
        ok = "✅" if d["correct"] else "❌"
        act = "回答" if d["actual_answerable"] else "拒答"
        exp = "应答" if d["expect_answerable"] else "应拒"
        st.write(f"{ok} [{exp}→{act}] {d['question']}")
        if d["actual_answerable"]:
            st.write(f"　　回答预览: {d['answer_preview']}")

st.divider()
st.caption(f"实验时间 {meta['time']} ｜ 模型 {meta.get('model', '')} ｜ "
           "脚本: test_review_benchmark.py ｜ 结果: data/benchmark_review.json")
