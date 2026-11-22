"""
build_cases.py —— 标注CSV → benchmark_cases.json 合成脚本（K2·B3）
================================
把标注环节（LABELING_PROTOCOL.md 第4节流程）的产出合成为
benchmark.run() 可直接加载的固定测试集，并生成双标一致性报告。

输入（均位于 benchmarks/ 目录）:
  documents.json     {key: 文件名}——全文登记表，
                     文件本体放在 labeling_docs/<文件名>（纯文本txt）
  labeling_*.csv     标注文件（每个标注者一份，template 不参与合成），
                     列: case_id,doc_key,claim_content,evidence_text,
                         quote_text,gold_verdict,gold_quote_alignment,
                         annotator,notes

处理规则:
  1. 校验: 标签合法性（verdict 三分类 / alignment true-false）、
     doc_key 已登记、claim_content 非空；不合法的行报错跳过
  2. 去重: 不同 case_id 但 (doc_key, claim_content) 相同视为重复，
     保留先出现的，重复的报 warn
  3. 双标: 按 case_id 分组——
     - 组内各标注 verdict 与 alignment 完全一致 → 直接作为 gold
     - 存在不一致 → 该条进入"待仲裁"清单，跳过不入库
       （仲裁由人工完成：改掉其中一份CSV的值后重跑本脚本）
     - 只有一份标注 → 入库但计入"单标样本"（答辩时需说明双标覆盖率）
  4. κ: 对双标一致的样本组计算 Cohen's κ（verdict 三分类 +
     alignment 二分类），对照验收线 0.70 / 0.80
  5. 配额: 按 LABELING_PROTOCOL.md 第2节配额表检查样本构成并打印

输出:
  benchmarks/benchmark_cases.json（格式与 benchmark.load_cases 的 A 格式兼容；
  覆盖前自动备份旧文件到 data/benchmark/）

使用方法:
  python benchmarks/build_cases.py             # 合成+报告+落盘
  python benchmarks/build_cases.py --dry-run   # 只校验+报告，不写文件
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_JSON = os.path.join(BENCH_DIR, "documents.json")
DOCS_DIR = os.path.join(BENCH_DIR, "labeling_docs")
OUT_PATH = os.path.join(BENCH_DIR, "benchmark_cases.json")

VALID_VERDICTS = ("supported", "unsupported", "contradicted")
VALID_ALIGN = {"true": True, "false": False, "1": True, "0": False,
               "yes": True, "no": False}

# LABELING_PROTOCOL.md 第2节配额表（类别 -> 最少条数）
QUOTA_RULES = [
    ("supported(对齐真)", lambda n: n["supported"]),
    ("unsupported", lambda n: n["unsupported"]),
    ("contradicted", lambda n: n["contradicted"]),
]
QUOTA_MIN = {"supported": 80, "unsupported": 50, "contradicted": 30}


def load_documents() -> dict[str, str]:
    """读documents.json + labeling_docs/，返回{key: 全文text}"""
    if not os.path.exists(DOCS_JSON):
        sys.exit(f"[build_cases] 缺少 {DOCS_JSON}——"
                 f"请按协议第4节登记 {{key: 文件名}}")
    with open(DOCS_JSON, "r", encoding="utf-8-sig") as f:
        registry = json.load(f)
    docs: dict[str, str] = {}
    for key, fname in registry.items():
        path = os.path.join(DOCS_DIR, fname)
        if not os.path.exists(path):
            print(f"[warn] 文档 {key} 指向的 {path} 不存在，"
                  f"引用它的样本将全部跳过")
            continue
        with open(path, "r", encoding="utf-8") as f:
            docs[key] = f.read()
    return docs


def load_annotations() -> list[dict]:
    """扫描labeling_*.csv（跳过template），返回校验后的标注行列表"""
    rows: list[dict] = []
    files = [f for f in sorted(os.listdir(BENCH_DIR))
             if f.startswith("labeling") and f.endswith(".csv")
             and "template" not in f]
    if not files:
        sys.exit("[build_cases] 找不到 labeling_*.csv——"
                 "请按协议第4节先完成标注（复制 labeling_template.csv）")
    for fname in files:
        path = os.path.join(BENCH_DIR, fname)
        with open(path, "r", encoding="utf-8-sig") as f:
            for ln, row in enumerate(csv.DictReader(f), start=2):
                row = {k: (v or "").strip() for k, v in row.items()}
                row["_src"] = f"{fname}:{ln}"
                rows.append(row)
    return rows


def validate(row: dict, docs: dict[str, str]) -> str | None:
    """校验单行，返回错误原因；None=通过"""
    v = row.get("gold_verdict", "").lower()
    if v not in VALID_VERDICTS:
        return f"gold_verdict 非法: {row.get('gold_verdict')!r}"
    a = row.get("gold_quote_alignment", "").lower()
    if a not in VALID_ALIGN:
        return f"gold_quote_alignment 非法: {row.get('gold_quote_alignment')!r}"
    if not row.get("case_id"):
        return "case_id 为空"
    if not row.get("claim_content"):
        return "claim_content 为空"
    if row.get("doc_key") not in docs:
        return f"doc_key {row.get('doc_key')!r} 未在 documents.json 登记"
    return None


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's κ（多分类通用）。完全一致或期望一致时特殊值处理。"""
    n = len(a)
    if n == 0:
        return 0.0
    cats = set(a) | set(b)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0
    return (po - pe) / (1.0 - pe)


def build(dry_run: bool = False) -> None:
    docs = load_documents()
    rows = load_annotations()

    # ---- 1. 校验 ----
    valid: list[dict] = []
    for row in rows:
        err = validate(row, docs)
        if err:
            print(f"[跳过] {row['_src']}: {err}")
        else:
            row["gold_verdict"] = row["gold_verdict"].lower()
            row["gold_quote_alignment"] = VALID_ALIGN[
                row["gold_quote_alignment"].lower()]
            valid.append(row)
    print(f"[build_cases] 有效标注 {len(valid)}/{len(rows)} 行"
          f"（{len(docs)} 篇登记文档）")

    # ---- 2. 按 case_id 分组做双标合并（去重必须在其后，否则会把
    #         双标者对同一条声明的一致标注误杀为"重复"）----
    groups: dict[str, list[dict]] = {}
    for row in valid:
        groups.setdefault(row["case_id"], []).append(row)

    cases: list[dict] = []
    conflicts: list[str] = []
    n_single = 0
    merged: list[tuple[tuple, dict, str]] = []  # (去重key, case, 来源)
    for cid, group in sorted(groups.items()):
        head = group[0]
        verdicts = {g["gold_verdict"] for g in group}
        aligns = {g["gold_quote_alignment"] for g in group}
        if len(group) > 1 and (len(verdicts) > 1 or len(aligns) > 1):
            detail = "; ".join(
                f"{g.get('annotator') or g['_src']}="
                f"{g['gold_verdict']}/{g['gold_quote_alignment']}"
                for g in group)
            conflicts.append(f"{cid}: {detail}")
            continue  # 待仲裁，不入库
        if len(group) == 1:
            n_single += 1
        case = {
            "case_id": cid,
            "arxiv_id": f"bench-{head['doc_key']}",
            "doc": head["doc_key"],
            "claim_content": head["claim_content"],
            "gold_verdict": head["gold_verdict"],
            "gold_quote_alignment": head["gold_quote_alignment"],
        }
        # 可选字段: 非空才写入（省略时 load_cases 展开为全文）
        if head.get("quote_text"):
            case["quote_text"] = head["quote_text"]
        if head.get("evidence_text"):
            case["evidence_text"] = head["evidence_text"]
        merged.append(((head["doc_key"], head["claim_content"]),
                       case, head["_src"]))

    # ---- 3. 跨case去重（不同case_id但同 doc_key+claim_content）----
    seen: dict[tuple, str] = {}
    for key, case, src in merged:
        if key in seen:
            print(f"[warn] 重复声明 {case['case_id']} ({src}) 与 "
                  f"{seen[key]} 相同，保留前者")
            continue
        seen[key] = case["case_id"]
        cases.append(case)

    # ---- 4. 双标一致性 κ ----
    double_groups = {cid: g for cid, g in groups.items() if len(g) > 1}
    print("\n" + "=" * 64)
    print("📋 双标一致性报告（Cohen's κ）")
    print("=" * 64)
    if not double_groups:
        print("  暂无双标样本（每条 case_id 仅出现一次）——"
              "验收要求每条由 2 人独立标注")
    else:
        paired = [(g[0], g[1]) for g in double_groups.values()]
        kv = cohen_kappa([p[0]["gold_verdict"] for p in paired],
                         [p[1]["gold_verdict"] for p in paired])
        ka = cohen_kappa([str(p[0]["gold_quote_alignment"]) for p in paired],
                         [str(p[1]["gold_quote_alignment"]) for p in paired])
        print(f"  双标样本: {len(paired)} 条 | verdict κ = {kv:.3f}"
              f"（验收线 0.70） | alignment κ = {ka:.3f}（验收线 0.80）")
        if kv < 0.70 or ka < 0.80:
            print("  ⚠ 未达验收线: 先修协议口径/组织仲裁，再继续扩标")
    if conflicts:
        print(f"\n  ⚠ 待仲裁 {len(conflicts)} 条（标注不一致，已跳过不入库）:")
        for c in conflicts:
            print(f"    {c}")
        print("  仲裁方式: 修正其中一份CSV后重跑本脚本")
    print(f"  单标样本: {n_single} 条（已入库，答辩需说明双标覆盖率）")

    # ---- 5. 配额检查 ----
    stats = {v: sum(1 for c in cases if c["gold_verdict"] == v)
             for v in VALID_VERDICTS}
    fake_quote = sum(1 for c in cases if not c["gold_quote_alignment"])
    print("\n" + "=" * 64)
    print("📊 样本构成（对照 LABELING_PROTOCOL.md 第2节配额表）")
    print("=" * 64)
    print(f"  总计 {len(cases)} 条 | supported {stats['supported']}"
          f"（配额≥{QUOTA_MIN['supported']}） | "
          f"unsupported {stats['unsupported']}"
          f"（配额≥{QUOTA_MIN['unsupported']}） | "
          f"contradicted {stats['contradicted']}"
          f"（配额≥{QUOTA_MIN['contradicted']}）")
    print(f"  引用伪造/改写样本（对齐=false）: {fake_quote} 条（配额≥30）")
    if len(cases) < 200:
        print(f"  ⚠ 总量 {len(cases)} < 200 条目标，继续扩标")
    print("=" * 64)

    if dry_run:
        print("[build_cases] --dry-run：不写文件")
        return
    if not cases:
        sys.exit("[build_cases] 没有可入库的样本，不覆盖现有测试集")

    # ---- 6. 落盘（覆盖前备份旧文件）----
    if os.path.exists(OUT_PATH):
        backup_dir = os.path.join(os.path.dirname(BENCH_DIR), "data",
                                  "benchmark")
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(
            backup_dir, f"benchmark_cases_backup_{stamp}.json")
        with open(OUT_PATH, "r", encoding="utf-8") as fin, \
                open(backup, "w", encoding="utf-8") as fout:
            fout.write(fin.read())
        print(f"[build_cases] 旧测试集已备份: {backup}")

    # documents 只保留被引用的 key
    used = {c["doc"] for c in cases}
    payload = {
        "_readme": [
            f"由 build_cases.py 于 {datetime.now().isoformat(timespec='seconds')}"
            f" 从标注CSV自动合成（协议 v3，LABELING_PROTOCOL.md）。",
            f"样本 {len(cases)} 条: supported {stats['supported']} / "
            f"unsupported {stats['unsupported']} / "
            f"contradicted {stats['contradicted']}；对齐false {fake_quote} 条。",
            "gold_verdict/gold_quote_alignment 为人工标注地面真值，"
            "只用于评测。",
        ],
        "documents": {k: docs[k] for k in sorted(used)},
        "cases": cases,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[build_cases] 已生成 {OUT_PATH}（{len(cases)} 条 / "
          f"{len(used)} 篇文档）")
    print("[build_cases] 运行 python benchmark.py 验证可加载")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="标注CSV→benchmark_cases.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="只校验与报告，不写文件")
    args = parser.parse_args()
    build(dry_run=args.dry_run)
