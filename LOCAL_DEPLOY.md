# 本地部署指南（协作者专用）

把本仓库部署到本地运行，功能与 Render 云端版完全一致（13 个标签页全功能）。
本地部署的优势：家用 IP 不被学术 API 限流（检索/引用图谱能拿全量数据）、
磁盘持久（PDF、任务历史、引用缓存重启不丢）。

## 前置条件

- Python 3.11+
- Git

## 步骤 1：克隆仓库

```bash
git clone https://github.com/Motis233/agent233.git
cd agent233
# 或从上游分支拉取：
# git clone -b local-deploy https://github.com/mimimichen666/albxx.git
```

## 步骤 2：安装依赖 + 配置密钥

```bash
python -m venv venv
venv\Scripts\activate          # Windows（Linux/macOS: source venv/bin/activate）
pip install -r requirements.txt
```

复制 `.env.example` 为 `.env`，填入：

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | LLM API（OpenAI 兼容格式，必填） |
| `LLM_API_KEY_2` / `LLM_BASE_URL_2` / `LLM_MODEL_2` | 第二路 LLM（并行核验用，可选） |
| `S2_API_KEY` | Semantic Scholar API key（提高检索稳定性，可选） |
| `APP_PASSWORD` | 网页访问密码（本地可不填；不填则无密码门） |

## 方式 A：直接运行（推荐，秒启动）

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 7860
```

浏览器打开 http://127.0.0.1:7860 即可使用。
这条命令就是 Render Dockerfile 里的启动命令，本地等效于云端部署。

## 方式 B：Docker 运行（与 Render 环境完全一致）

需要 Docker Desktop：

```bash
docker build -t litagent .
docker run -d -p 7860:7860 --env-file .env litagent
```

访问 http://localhost:7860。适用于复现/排查云端特有问题。

## 使用入口

- 主界面：`http://127.0.0.1:7860`（由 `server.py` + `static/index.html` 提供）
- 老 Streamlit 页面（可选）：`streamlit run app.py`
- 任务数据落在 `data/`，产物落在 `output/`，均为本地持久化

## 常见问题

1. **检索阶段失败「没有获得可用论文」**：多为 Semantic Scholar/OpenAlex 限流，
   等待重试或配置 `S2_API_KEY`（本地家用 IP 通常不会触发）。
2. **PDF 全文搜索不可用**：确认安装了 PyMuPDF（requirements.txt 已含）。
3. **Word 导出报 No module named docx**：重装依赖 `pip install -r requirements.txt`。
4. **端口占用**：改用 `--port 7861` 等其他端口。
