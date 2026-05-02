# MinerU Batch

批量 PDF 解析工具，基于 MinerU API。

## 快速启动

```bash
# 一键生产模式（自动构建前端 + 单进程运行）
make prod
```

访问 http://localhost:8900

## 开发模式

前后端分离运行，支持前端热更新（HMR）：

```bash
make dev
```

或分别启动：

```bash
# 后端
cd backend && DEV_MODE=1 uvicorn main:app --host 0.0.0.0 --port 8900 --reload

# 前端（另开终端）
cd frontend && npm run dev
```

开发模式下前端访问 http://localhost:3001，API 请求自动代理到后端。

## 其他命令

```bash
make build    # 仅构建前端
make test     # 运行后端测试
make clean    # 清理构建产物
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEV_MODE` | 无 | 设为 `1` 跳过静态文件服务，使用 Vite dev server |
| `CORS_ORIGINS` | 无 | 允许的跨域来源（逗号分隔），生产模式下无需设置 |

## 目录结构

```
backend/
  main.py        # FastAPI 入口 + 前端静态服务
  routes.py      # API 路由
  models.py      # SQLAlchemy 模型
  tests/         # pytest 测试套件（45 tests）
  requirements.txt

frontend/
  src/           # Vue 3 + TypeScript
  public/        # 静态资源
  vite.config.ts
```

## 依赖

- Python 3.10+
- Node.js 18+
- MinerU API 服务 (默认 localhost:8086)
- VLLM/OpenAI 兼容服务 (默认 localhost:6002)
