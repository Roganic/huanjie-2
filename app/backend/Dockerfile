# 幻界 2.0 后端 Dockerfile
# 支持 Railway、Render 等云平台部署

FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# 复制源代码
COPY src ./src

# 暴露端口 (由平台通过 PORT 环境变量提供)
EXPOSE 8000

# 启动命令
# 使用 0.0.0.0 绑定以接受外部连接
CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
