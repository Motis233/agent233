# 科研文献整理 Agent

基于**多 Agent 协作架构**的文献综述自动生成系统：输入一个研究主题，自动完成"检索 → 提取 → 审查 → 综合"全流程，产出带防幻觉核验的综述报告、证据链可穿透的信息卡片和交互式引用图谱。

> 课程项目：组装现有模型（LLM API）成智能体，**不训练任何新模型**。

## 一、系统架构

```
用户主题（如"脉冲神经网络的高效训练方法"）
        │
        ▼
┌─────────────────┐   检索计划: 检索词/经典论文清单/筛选标准
│  1. 规划 Agent   │────────────────────────┐
└─────────────────┘                        ▼
┌─────────────────────────────────────────────────┐
│  2. 检索 Agent（四路信号召回 + 综合排序）          │
│  ├─ 关键词双路: 影响力路(被引排序) + 相关性路      │
│  ├─ 引用链挖掘: 种子论文参考文献共被引统计         │
│  │   （含雪球扩展: 顶级经典作二级种子再挖一层）    │
│  └─ LLM领域先验: 按经典标题反查收录               │
│  → RRF融合 + 四路加权: 相关性45% + RRF20%         │
│     + 影响力15% + 引用链20%                       │
└─────────────────────────────────────────────────┘
        │  PaperMeta列表（含PDF）
        ▼
┌─────────────────┐   PaperCard: 方法/结果/局限声明
│  3. 提取 Agent   │   + 原文逐字引用(防幻觉基石)
└─────────────────┘
        │
        ▼
┌─────────────────┐   两级核验: 程序对齐检查(逐字匹配)
│  4. 审查 Agent   │   + LLM语义一致性 → 幻觉率报告
└─────────────────┘
        │
        ▼
┌─────────────────┐   综述报告 + 方法对比表格
│  5. 综合 Agent   │   + 交互式引用图谱(pyvis)
└─────────────────┘
```

## 二、核心特性

### 1. 检索质量：经典论文召回体系
关键词检索有系统性盲区——奠基论文（如 SpikeProp 1999）的摘要不含现代术语，永远检索不到。本项目用四路信号解决：

| 信号 | 原理 | 代表论文 |
|---|---|---|
| 引用链挖掘 | 被多篇种子论文共同引用 = 领域经典 | SLAYER、Spatio-Temporal BP |
| 雪球扩展 | 顶级经典的参考文献里必有更老的经典 | BPTT(1990)、LeNet(1998) |
| LLM领域先验 | 规划Agent直接给出经典标题，按标题反查 | SpikeProp、Tempotron |
| 经典免检通道 | 共被引≥3 的论文跳过LLM粗筛（学术界共识 > 单次LLM判断） | 被引1000+的奠基作 |

### 2. 可信机制（防幻觉三件套）
- **两级审查**：程序逐字对齐（抓伪造引用）+ LLM语义核验（抓改写失真），量化幻觉率
- **证据链穿透**：每条声明可定位到 PDF 原文页面并高亮，点击即查证
- **可信问答**：回答仅基于已核验声明池，无依据时明确拒答（拒绝幻觉）
- **矛盾检测**：跨论文发现学术争议（直接矛盾 + 观点张力）

### 3. 前端（Streamlit，8 个标签页）
🔍 检索结果（四维排序切换+经典徽章） / 📄 信息卡片 / ✅ 审查明细 / 💬 可信问答 / ⚡ 学术争议 / 📊 综述表格 / 🕸 引用图谱 / 📝 最终报告

## 三、快速开始

### 1. 环境准备

```powershell
# 克隆仓库
git clone https://github.com/mimimichen666/-.git
cd -

# Python 3.10+，安装依赖
pip install -r requirements.txt
```

### 2. 配置密钥

```powershell
# 复制模板并填入你的密钥（.env 已被 gitignore 排除，不会提交）
copy .env.example .env
```

`.env` 需要填的项：

| 键 | 说明 | 申请地址 |
|---|---|---|
| `LLM_API_KEY` | LLM密钥（必填） | [DeepSeek](https://platform.deepseek.com) 或 [智谱GLM](https://open.bigmodel.cn)（glm-4-flash 有免费额度） |
| `LLM_BASE_URL` | API地址 | 默认 `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` / `glm-4-flash` |
| `S2_API_KEY` | Semantic Scholar密钥（可选） | [免费申请](https://www.semanticscholar.org/product/api#form)，可大幅缓解限流 |

### 3. 启动

```powershell
streamlit run app.py --server.port 8501
```

浏览器访问 **http://127.0.0.1:8501**（注意用 `127.0.0.1`，本机 localhost 可能被 VPN 劫持）。

侧边栏输入主题 → 点击 **🚀 完整运行**（约 10-15 分钟）→ 8 个标签页自动填充。
也可以点 **📂 载入已有结果** 直接查看 `data/`、`output/` 里的历史产出。

> ⚠️ **主题要具体**："llm" 这种宽泛主题会产生 200+ 候选拖慢检索；写"大语言模型的幻觉抑制方法"这类具体主题效果最佳。

## 四、目录结构

```
├── app.py                  # Streamlit 前端入口（8标签页）
├── config.py               # 配置（密钥从.env读取，无硬编码）
├── models.py               # Pydantic数据契约（Agent间传递的结构）
├── llm_client.py           # LLM调用封装（含重试/用量统计）
├── agents/
│   ├── planner.py          # 规划: 主题→检索计划+经典论文清单
│   ├── searcher.py         # 检索: 四路召回+RRF融合+综合排序+PDF下载
│   ├── extractor.py        # 提取: PDF→信息卡片(声明+逐字引用)
│   ├── reviewer.py         # 审查: 两级核验→幻觉率报告
│   ├── synthesizer.py      # 综合: 综述报告+表格+引用图谱
│   ├── evidence_locator.py # 证据链: 引用定位到PDF页面并高亮
│   ├── qa_agent.py         # 可信问答(声明池约束+拒答)
│   └── conflict_detector.py# 矛盾检测(预筛+LLM语义判断)
├── lib/                    # 前端JS库(vis网络图/tom-select)
├── papers/                 # 下载的PDF（gitignore，本地生成）
├── data/                   # 证据库JSON（gitignore，本地生成）
├── output/                 # 报告/表格/图谱（gitignore，本地生成）
├── evidence/               # 高亮截图缓存（gitignore，本地生成）
├── test_*.py               # 各环节验证脚本
├── sync.ps1 / sync.bat     # 一键同步到GitHub
├── .env.example            # 密钥配置模板
└── requirements.txt        # 依赖清单
```

## 五、团队协作规范

### 日常同步（一键）

```powershell
# 有改动时，双击 sync.bat 或：
.\sync.ps1 "你改了什么"
```

脚本自动完成：检测改动 → 拉取组员更新（rebase）→ 提交 → 推送。

### 手动流程（理解原理用）

```powershell
git add -A                    # 暂存所有改动
git commit -m "说明"          # 提交
git pull --rebase origin main # 先拉组员的更新
git push origin main          # 推送
```

### 注意事项

1. **绝不提交密钥**：`.env` 已被 gitignore；新增配置一律走环境变量
2. **运行时目录不入库**：`papers/`（717MB PDF）、`data/`、`output/` 都是本地生成物
3. **检索 Agent 的 API 限速**：OpenAlex 限 10 万次/天，但**并发流水线会触发 429 封锁**——前端已加运行锁，流水线执行中请勿重复点击"完整运行"，被封锁后需零请求冷却 10 分钟以上
4. **提交信息用中文**，说清楚"改了什么、为什么"

## 六、验证脚本

| 脚本 | 用途 |
|---|---|
| `test_e2e.py` | 端到端全流程（规划→检索→提取→审查→综合→证据定位→矛盾检测） |
| `test_chain.py` | 引用链挖掘+经典召回+四路排序验证 |
| `test_qa.py` | 可信问答拒答机制回归测试 |
| `test_conflict.py` | 矛盾检测验证 |
| `test_rrf.py` | RRF融合排序验证 |

运行方式：`python -u test_xxx.py`（建议先跑 `test_e2e.py` 确认环境正常）
