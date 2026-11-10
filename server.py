# -*- coding: utf-8 -*-
"""
server.py —— FastAPI 任务服务器（方案一：前端与执行彻底解耦）
================================================================
替代 Streamlit 的执行模型：
  - POST /api/run       提交任务，立即返回 task_id（页面不再被任务阻塞）
  - GET  /api/tasks     任务列表（历史可查回）
  - GET  /api/tasks/{id}/stream   SSE 实时推送进度（阶段/日志/终态）
  - POST /api/tasks/{id}/cancel   置取消标志，worker 在阶段边界优雅退出
  - GET  /api/tasks/{id}/result   报告+论文+矛盾+核验结果
  - GET  /api/tasks/{id}/graph    引用图谱（HTML）

任务隔离（不改动任何 agents 代码的前提下）：
  - 流水线 worker 仍写共享的 data/pipeline_status.json（同一时刻只有一个
    活跃任务，第二个提交会收到 409 提示）；
  - 每个任务终态时把产物快照进 data/tasks/<id>/，刷新/重启后历史仍可查回；
  - SSE 只对活跃任务直播进度；历史任务直接返回快照终态。

鉴权：若配置 APP_PASSWORD，所有 /api/* 要求头 X-App-Password 或
查询参数 ?pw=（SSE 的 EventSource 无法自定义头，走 query 参数）。

运行: uvicorn server:app --host 0.0.0.0 --port 7860
(HF Spaces 要求监听 7860 端口；本地可用 PORT 环境变量覆盖)
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

import config

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE = config.PROJECT_ROOT
DATA = config.DATA_DIR
OUTPUT = config.OUTPUT_DIR
STATIC = os.path.join(BASE, "static")
WORKER = os.path.join(BASE, "pipeline_worker.py")
TASKS_DIR = os.path.join(DATA, "tasks")          # 每任务快照目录
REGISTRY = os.path.join(DATA, "tasks.json")      # 任务注册表
STATUS_FILE = os.path.join(DATA, "pipeline_status.json")
PROGRESS_FILE = os.path.join(DATA, "pipeline_progress.jsonl")
CANCEL_FLAG = os.path.join(DATA, "pipeline_cancel.flag")

# 各阶段产物 → 快照时的目标名（None 表示该文件不存在时跳过）
_SNAPSHOT_FILES = [
    ("final_report.md", os.path.join(OUTPUT, "final_report.md")),
    ("review_table.md", os.path.join(OUTPUT, "review_table.md")),
    ("citation_graph.html", os.path.join(OUTPUT, "citation_graph.html")),
    ("papers.json", os.path.join(DATA, "pipeline_papers.json")),
    ("paper_cards.json", os.path.join(DATA, "paper_cards.json")),
    ("review_results.json", os.path.join(DATA, "review_results.json")),
    ("conflicts.json", os.path.join(DATA, "conflicts.json")),
    ("evidence_index.json", os.path.join(DATA, "evidence_index.json")),
    ("plan.json", os.path.join(DATA, "plan_last.json")),
    ("glossary.json", os.path.join(DATA, "glossary_last.json")),
]

_lock = threading.Lock()          # 保护注册表读写与任务提交互斥

app = FastAPI(title="文献综述 Agent")


# ----------------------------------------------------------------
# 注册表（data/tasks.json：任务列表持久化，容器存活期内可查回）
# ----------------------------------------------------------------
def _load_tasks() -> list[dict]:
    if os.path.exists(REGISTRY):
        try:
            with open(REGISTRY, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_tasks(tasks: list[dict]) -> None:
    os.makedirs(DATA, exist_ok=True)
    tmp = REGISTRY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REGISTRY)


def _active(tasks: list[dict]) -> dict | None:
    return next((t for t in tasks if t.get("state") == "running"), None)


def _find(tasks: list[dict], tid: str) -> dict | None:
    return next((t for t in tasks if t.get("id") == tid), None)


def _task_dir(tid: str) -> str:
    return os.path.join(TASKS_DIR, tid)


# ----------------------------------------------------------------
# 鉴权（APP_PASSWORD 可选）
# ----------------------------------------------------------------
def _check_auth(request: Request, pw: str = "") -> None:
    secret = getattr(config, "APP_PASSWORD", "")
    if not secret:
        return
    got = request.headers.get("X-App-Password") or request.query_params.get("pw", "")
    if got != secret:
        raise HTTPException(401, "需要访问密码（X-App-Password 头或 ?pw= 参数）")


# ----------------------------------------------------------------
# 任务生命周期
# ----------------------------------------------------------------
def _spawn(task: dict) -> subprocess.Popen:
    """启动 worker 子进程，stdout/stderr 重定向到任务的运行日志。
    返回 Popen 句柄（仅存于内存传给 watcher；注册表只记 pid）"""
    log_path = os.path.join(_task_dir(task["id"]), "run.log")
    logf = open(log_path, "w", encoding="utf-8")
    cmd = [sys.executable, WORKER,
           "--topic", task["topic"],
           "--top_k", str(task["top_k"]),
           "--mode", task["mode"],
           "--years", str(task["years"])]
    if task.get("fast"):
        cmd.append("--fast")
    proc = subprocess.Popen(cmd, cwd=BASE, stdout=logf, stderr=logf)
    task["pid"] = proc.pid
    return proc


def _snapshot(task: dict, state: str) -> None:
    """终态时把共享 data/output 的产物复制进 data/tasks/<id>/"""
    d = _task_dir(task["id"])
    os.makedirs(d, exist_ok=True)
    for name, path in _SNAPSHOT_FILES:
        try:
            if os.path.exists(path):
                shutil.copy2(path, os.path.join(d, name))
        except OSError:
            pass
    task["state"] = state
    task["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _read_status() -> dict:
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _watcher(task: dict) -> None:
    """后台线程：跟踪活跃任务直到终态，然后落快照"""
    while True:
        time.sleep(1.0)
        tasks = _load_tasks()
        cur = _find(tasks, task["id"])
        if cur is None:            # 注册表被清空等异常情况
            return
        st = _read_status()
        state = st.get("state")
        proc = task.get("_proc")
        # 状态文件出现终态，或进程已退出 → 收尾
        terminal = {"done", "error", "cancelled"}
        if state in terminal:
            with _lock:
                tasks = _load_tasks()
                cur = _find(tasks, task["id"])
                if cur and cur.get("state") == "running":
                    _snapshot(cur, state)
                    _save_tasks(tasks)
            return
        if proc is not None and proc.poll() is not None:
            # 进程退出但状态文件没写成终态（如被强杀）→ 兜底标记 error
            with _lock:
                tasks = _load_tasks()
                cur = _find(tasks, task["id"])
                if cur and cur.get("state") == "running":
                    _snapshot(cur, "error")
                    cur["msg"] = f"worker 进程退出码 {proc.returncode}"
                    _save_tasks(tasks)
            return


@app.post("/api/run")
async def api_run(request: Request):
    body = await request.json()
    _check_auth(request)
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "topic 不能为空")
    mode = body.get("mode", "standard")
    if mode not in ("standard", "mode1", "mode2", "mode3"):
        raise HTTPException(400, f"不支持的检索模式: {mode}")

    with _lock:
        tasks = _load_tasks()
        act = _active(tasks)
        if act:
            raise HTTPException(
                409, f"已有任务在运行（{act['topic'][:20]}…），请等待完成或先取消")
        tid = uuid.uuid4().hex[:8]
        task = {
            "id": tid,
            "topic": topic,
            "mode": mode,
            "fast": bool(body.get("fast")),
            "top_k": int(body.get("top_k", 6)),
            "years": int(body.get("years", 2)),
            "state": "running",
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        os.makedirs(_task_dir(tid), exist_ok=True)
        tasks.insert(0, task)
        _save_tasks(tasks)
        proc = _spawn(task)
        task["_proc"] = proc          # 仅内存，watcher 用于兜底判活
    threading.Thread(target=_watcher, args=(task,), daemon=True).start()
    return {"id": tid, "state": "running"}


@app.get("/api/tasks")
async def api_tasks(request: Request):
    _check_auth(request)
    tasks = _load_tasks()
    return [{"id": t["id"], "topic": t["topic"], "mode": t["mode"],
             "fast": t.get("fast"), "state": t["state"],
             "submitted_at": t.get("submitted_at"),
             "finished_at": t.get("finished_at"),
             "hallucination_rate": t.get("hallucination_rate"),
             "msg": t.get("msg")} for t in tasks[:50]]


@app.get("/api/tasks/{tid}")
async def api_task(tid: str, request: Request):
    _check_auth(request)
    tasks = _load_tasks()
    t = _find(tasks, tid)
    if not t:
        raise HTTPException(404, "任务不存在")
    info = {k: t.get(k) for k in
            ("id", "topic", "mode", "fast", "state", "submitted_at",
             "finished_at", "hallucination_rate", "msg")}
    if t["state"] == "running":
        info["live"] = _read_status()     # 活跃任务附带实时状态
    return info


@app.post("/api/tasks/{tid}/cancel")
async def api_cancel(tid: str, request: Request):
    _check_auth(request)
    tasks = _load_tasks()
    t = _find(tasks, tid)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t["state"] != "running":
        raise HTTPException(400, f"任务已是终态（{t['state']}），无需取消")
    open(CANCEL_FLAG, "w").close()        # worker 在阶段边界发现即退出
    return {"ok": True, "msg": "取消标志已置位，将在当前阶段结束后停止"}


@app.get("/api/tasks/{tid}/stream")
async def api_stream(tid: str, request: Request, pw: str = ""):
    _check_auth(request, pw)
    tasks = _load_tasks()
    t = _find(tasks, tid)
    if not t:
        raise HTTPException(404, "任务不存在")

    def gen():
        offset = 0
        last_state = None
        import time as _t
        deadline_idle = 0
        while True:
            tasks = _load_tasks()
            cur = _find(tasks, tid)
            if cur is None:
                yield f"data: {json.dumps({'type': 'end', 'state': 'gone'})}\n\n"
                return
            # 1) 推送新追加的进度日志行
            try:
                with open(PROGRESS_FILE, encoding="utf-8") as f:
                    f.seek(offset)
                    lines = f.readlines()
                    offset = f.tell()
            except OSError:
                lines = []
            for ln in lines:
                try:
                    ev = json.loads(ln)
                    yield f"data: {json.dumps({'type': 'log', **ev}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
            # 2) 推送状态变化
            tasks = _load_tasks()
            cur = _find(tasks, tid)
            state = cur["state"]
            if state != last_state:
                payload = {"type": "state", "state": state,
                           "msg": cur.get("msg"),
                           "hallucination_rate": cur.get("hallucination_rate")}
                if state == "running":
                    st = _read_status()
                    payload.update({"stage": st.get("stage"),
                                    "status_msg": st.get("msg")})
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last_state = state
            if state != "running":
                yield f"data: {json.dumps({'type': 'end', 'state': state})}\n\n"
                return
            # worker 进程死了但注册表还没更新（watcher 1s 内会收尾），最多等20轮
            if not lines:
                deadline_idle += 1
                if deadline_idle > 20:
                    yield f"data: {json.dumps({'type': 'state', 'state': 'running', 'stage': '…'})}\n\n"
            _t.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/tasks/{tid}/result")
async def api_result(tid: str, request: Request):
    _check_auth(request)
    d = _task_dir(tid)
    if not os.path.isdir(d):
        raise HTTPException(404, "任务无产物（尚未运行完成或快照丢失）")
    out: dict = {"id": tid}
    files = {"report": "final_report.md", "review_table": "review_table.md",
             "papers": "papers.json", "cards": "paper_cards.json",
             "review": "review_results.json", "conflicts": "conflicts.json",
             "evidence": "evidence_index.json", "plan": "plan.json"}
    for key, name in files.items():
        p = os.path.join(d, name)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                txt = f.read()
            out[key] = json.loads(txt) if name.endswith(".json") else txt
        except Exception:
            continue
    return out


@app.get("/api/tasks/{tid}/graph")
async def api_graph(tid: str, request: Request):
    _check_auth(request)
    p = os.path.join(_task_dir(tid), "citation_graph.html")
    if not os.path.exists(p):
        raise HTTPException(404, "该任务没有引用图谱")
    return FileResponse(p, media_type="text/html")


@app.get("/api/pdf/{arxiv_id}")
async def api_pdf(arxiv_id: str, request: Request):
    _check_auth(request)
    safe = os.path.basename(arxiv_id).replace(".pdf", "")
    p = os.path.join(config.PAPER_DIR, safe + ".pdf")
    if not os.path.exists(p):
        raise HTTPException(404, "PDF 不存在（容器重启后 papers/ 会清空）")
    return FileResponse(p, media_type="application/pdf")


@app.get("/api/health")
async def api_health():
    return {"ok": True, "app_password": bool(getattr(config, "APP_PASSWORD", ""))}


# 静态前端（放在最后，避免吞掉 /api/*）
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0",
                port=int(os.environ.get("PORT", "7860")))
