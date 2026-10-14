"""
benchmark.py —— 固定 Benchmark 评测入口（阶段4）
================================
职责：
  1. load_cases(): 加载固定测试集 benchmarks/benchmark_cases.json
     （支持 {documents, cases} 结构：case 通过 doc 字段引用文档，
      加载时展开为 full_text/evidence_text；也兼容逐条内联的旧格式）
  2. run(): 对固定测试集运行审查器（run_d_benchmark），产出
     Precision/Recall/F1（逐类+Macro）、误放行率等指标并落盘
  3. compare(): 比较两次评测报告，量化"修改前后"的指标变化

使用方法：
  python benchmark.py                    # 运行当前审查器并保存报告
  python benchmark.py compare old.json new.json   # 比较两份历史报告

指标口径（与 agents/reviewer.py 统一）：
  - Precision/Recall/F1: 按 supported/unsupported/contradicted 逐类计算
  - Macro-F1: 三类F1平均
  - 误放行率: gold坏声明(判定!=supported 或 引用伪造)被预测放行的比例
  - LLM调用失败的样本计入 errored_cases，跳过不评测（不伪造判定）
"""

import os
import json
import sys
from datetime import datetime

import config
from agents.reviewer import run_d_benchmark
from models import BenchmarkCase

# 固定测试集目录（随仓库版本控制）
BENCH_DIR = os.path.join(config.PROJECT_ROOT, "benchmarks")
CASES_PATH = os.path.join(BENCH_DIR, "benchmark_cases.json")
# 评测报告输出目录（运行时产物，不入仓库）
OUT_DIR = os.path.join(config.DATA_DIR, "benchmark")
REPORT_PATH = os.path.join(OUT_DIR, "benchmark_report.json")


def load_cases(path: str = CASES_PATH) -> list[BenchmarkCase]:
    """
    加载固定测试集

    兼容两种格式:
      A) {"documents": {key: text}, "cases": [{..., "doc": key}]}
         -> 展开 full_text=documents[doc]，evidence_text缺省也用documents[doc]
      B) [{case...}, ...] 逐条内联 full_text/evidence_text（旧格式/单文件测试）
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        return [BenchmarkCase(**item) for item in raw]

    documents = raw.get("documents", {})
    cases: list[BenchmarkCase] = []
    for item in raw.get("cases", []):
        item = {k: v for k, v in item.items() if not k.startswith("_")}
        doc_key = item.pop("doc", None)
        if doc_key is not None:
            doc_text = documents[doc_key]
            item.setdefault("full_text", doc_text)
            item.setdefault("evidence_text", doc_text)
        cases.append(BenchmarkCase(**item))
    return cases


def run(save: bool = True) -> "BenchmarkReport":
    """运行固定Benchmark并打印完整指标，可选落盘报告。"""
    from models import BenchmarkReport  # noqa: F401 (类型提示用)

    cases = load_cases()
    print(f"[Benchmark] 加载固定测试集: {len(cases)} 例 ({CASES_PATH})")
    report = run_d_benchmark(cases)

    if save:
        os.makedirs(OUT_DIR, exist_ok=True)
        payload = report.model_dump()
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        # 带时间戳的存档（供compare做"修改前后"对比）
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = os.path.join(OUT_DIR, f"benchmark_report_{stamp}.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[Benchmark] 报告已保存: {REPORT_PATH}")
        print(f"[Benchmark] 存档(供前后对比): {archive}")
    return report


def _get(report: dict, key: str, default=0.0):
    return report.get(key, default) if isinstance(report, dict) else getattr(report, key, default)


def compare(old_path: str, new_path: str) -> None:
    """
    比较两份Benchmark报告，输出"修改前后"的指标变化表。

    比较维度: Verdict Accuracy / Alignment Accuracy / Macro-F1 /
    误放行率 / 逐类F1。
    """
    with open(old_path, "r", encoding="utf-8") as f:
        old = json.load(f)
    with open(new_path, "r", encoding="utf-8") as f:
        new = json.load(f)

    rows = [
        ("Verdict Accuracy", _get(old, "verdict_accuracy"), _get(new, "verdict_accuracy")),
        ("Alignment Accuracy", _get(old, "alignment_accuracy"), _get(new, "alignment_accuracy")),
        ("Macro-F1", _get(old, "macro_f1"), _get(new, "macro_f1")),
        ("误放行率(越低越好)", _get(old, "false_pass_rate"), _get(new, "false_pass_rate")),
    ]
    for label in ("supported", "unsupported", "contradicted"):
        old_f1 = (_get(old, "f1") or {}).get(label, 0.0)
        new_f1 = (_get(new, "f1") or {}).get(label, 0.0)
        rows.append((f"F1[{label}]", old_f1, new_f1))

    print("\n" + "=" * 60)
    print("📊 Benchmark 前后对比")
    print(f"  旧: {old_path}  (n={_get(old, 'total_cases', '?')})")
    print(f"  新: {new_path}  (n={_get(new, 'total_cases', '?')})")
    print("=" * 60)
    print(f"{'指标':<24}{'修改前':>10}{'修改后':>10}{'变化':>10}")
    print("-" * 60)
    for name, o, n in rows:
        delta = n - o
        sign = "+" if delta >= 0 else ""
        arrow = "↑" if delta > 1e-9 else ("↓" if delta < -1e-9 else "→")
        print(f"{name:<24}{o:>10.3f}{n:>10.3f}{sign}{delta:>8.3f} {arrow}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        run()
