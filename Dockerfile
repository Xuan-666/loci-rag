# Loci · 本地知识库 RAG 智能问答系统 — Docker 镜像
# 基于 Python 3.12-slim,适合作为 CI / 一键部署使用。
#
# 注意:本镜像仅包含 Python 后端 + 前端。LLM 推理 (Ollama) 建议
# 通过 docker-compose 单独拉起 ollama 服务,避免镜像过大。
#
# 构建:  docker build -t loci-rag .
# 运行:  docker run -p 7862:7862 -v $(pwd)/data:/app/data loci-rag
# 配合 compose: 见仓库根目录 docker-compose.yml

FROM python:3.12-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # HuggingFace 离线模式(模型需提前下载挂载)
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# 创建工作目录
WORKDIR /app

# 安装系统依赖(用于构建 sentence-transformers / torch 的 wheel)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 1. 先复制 requirements.txt,利用 Docker 缓存
COPY requirements.txt .

# 2. 安装 Python 依赖(包含 torch CPU 版)
#    若你使用 GPU,改为:
#      pip install torch --index-url https://download.pytorch.org/whl/cu121
#    并加上 --gpus all 运行参数
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# 3. 复制项目源码
COPY . .

# 4. 创建运行时数据目录(将挂载到 host)
RUN mkdir -p /app/data/uploaded_docs \
             /app/data/vector_store \
             /app/data/vector_store_versions

# 5. 暴露端口
EXPOSE 7862

# 6. 健康检查(简单 TCP 探活)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:7862/api/health || exit 1

# 7. 启动 Web 服务
#    使用 waitress 作为生产 WSGI(若 requirements 已加)
CMD ["python", "web_api.py"]
