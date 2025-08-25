# 使用 Python 3.12 官方 slim 镜像
FROM python:3.12-slim

# 安装系统依赖（如需编译bcrypt等）
RUN apt-get update && \
    apt-get install -y --no-install-recommends apt-utils build-essential libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# 创建非root用户
RUN useradd -m appuser

# 设置工作目录
WORKDIR /app
# 安装依赖并升级 pip
RUN pip install --upgrade pip
# 复制依赖列表并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade --root-user-action=ignore -r requirements.txt

# 复制项目代码（不包含__pycache__，通过.dockerignore/.gcloudignore实现）
COPY . .

# 确保应用代码权限正确
RUN chown -R appuser:appuser /app

# 切换到非root用户
USER appuser

# Cloud Run 要求监听 0.0.0.0:8080，入口为 app.main:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]

# 可选：健康检查端点（Cloud Run 可自动检测 /）
#HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
#  CMD curl --fail http://localhost:8080/ || exit 1