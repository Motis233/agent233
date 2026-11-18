# HF Spaces Docker 部署：FastAPI 任务服务器（server.py）
FROM python:3.11-slim

WORKDIR /app

# 仅安装 API 服务所需依赖（不含 streamlit，缩短构建时间）
RUN pip install --no-cache-dir \
    "PyMuPDF>=1.28" \
    "arxiv>=4.0" \
    "pyvis==0.3.2" \
    "openai>=2.41" \
    "pydantic>=2.13" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "python-docx>=1.1" \
    "requests>=2.31"

COPY . .

ENV PYTHONUNBUFFERED=1

# HF Spaces 要求容器监听 7860
EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
