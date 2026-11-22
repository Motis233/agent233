# Benchmark 标注协议 v3（K2·B3：扩样本 + 双标一致性）

> 目标：把固定测试集从"15篇论文几十条声明"扩到 **200+ 条人工标注声明**，
> 并以双标注者一致性（Cohen's κ）支撑指标的可信度。
> 本文是唯一标注口径；与代码中 `agents/reviewer.py` 的判定标准同步维护。

---

## 1. 标签定义（三分类 verdict + 引用对齐 bool）

### gold_verdict（语义真值）

| 标签 | 定义 | 典型信号 |
|---|---|---|
| `supported` | 原文片段明确支撑声明的全部关键断言 | 数字/结论/方法归属全部能在原文找到；允许无害的近义改写 |
| `unsupported` | 原文片段撑不起声明的全部内容（缺证据/扩大范围/模糊化） | 原文说"在X数据集上"，声明说"在多个数据集上"；原文"提升12%"，声明只说"显著提升"；原文未提及但声明断言 |
| `contradicted` | 原文片段与声明直接冲突 | 数字对不上（原文12%声明13%）；方向相反（原文下降声明上升）；归属张冠李戴 |

判定优先级：先查是否 `contradicted`（有直接冲突才判），再查是否 `supported`（全部关键断言有着落才判），否则一律 `unsupported`。**宁严勿宽**——拿不准判 `unsupported`。

### gold_quote_alignment（引用对齐真值）

- `true`：quote_text 是 full_text 的**逐字连续片段**（空格/换行差异可忽略）
- `false`：quote 有任何改写、拼接（中间加省略号后接不上）、或整段编造

判定方法：在 full_text 里 Ctrl+F 搜索 quote 的一个 8-12 词连续片段；搜不到即 `false`。

## 2. 样本构成配额（200+ 条）

| 类别 | 数量 | 说明 |
|---|---|---|
| supported + 对齐 | ≥80 | 主干正样本 |
| unsupported（模糊化/扩范围/缺证据） | ≥50 | 重点：含 20 条数值模糊化（"提升12%"→"显著提升"类，验证K1数值校验） |
| contradicted（数字篡改/方向反转/张冠李戴） | ≥30 | 含 10 条纯数字篡改 |
| 引用伪造（quote 改写/编造，verdict 可为任意值） | ≥30 | 验证一级程序对齐 |
| 边界难例（长句多断言、部分支撑） | ≥20 | 用于拉开模型差距 |

来源：已下载论文（`papers/` 目录）随机抽取；每篇论文最多贡献 8 条（防止单篇偏置）。

## 3. 双标一致性（Cohen's κ）

- 每条样本由 **2 名标注者**独立标注（互不通气）
- κ = (观察一致率 − 期望一致率) / (1 − 期望一致率)
- 验收线：verdict 三分类 **κ ≥ 0.70**（substantial）；alignment 二分类 κ ≥ 0.80
- 不一致样本由第 3 人（或讨论）仲裁，仲裁结果为最终 gold；仲裁比例 > 20% 时说明本协议口径不清，先修协议再继续标

## 4. 操作流程

1. 复制 `labeling_template.csv` 为 `labeling_round1.csv`（每人一份，文件名加标注者缩写）
2. 论文全文放入 `benchmarks/labeling_docs/`，并在 `documents.json` 登记 `{key: 文件名}`
3. CSV 里 `doc_key` 填 documents.json 的 key（**全文不要内联进CSV**）
4. 标完交 `build_cases.py` 合成 `benchmark_cases.json`（自动去重、校验标签合法、生成双标一致性报告）

## 5. 与系统指标的对应

| 系统指标 | 由哪些样本支撑 |
|---|---|
| Verdict Accuracy / 逐类 P/R/F1 | 全部样本 |
| 误放行率 | gold_verdict != supported 或 gold_quote_alignment = false 的样本 |
| 消融实验（`python benchmark.py ablation`） | 需要样本带 quote_text + full_text（纯语义评测的样本消融时会被跳过） |
| 置信区间 | 自动计算（bootstrap 2000次），无需额外标注 |
