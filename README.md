# MinerU Batch

批量 PDF 解析工具，基于 MinerU API。

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8900 --reload

# 前端
cd frontend
npm install
npm run dev
```

访问 http://localhost:3001

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CORS_ORIGINS` | `http://localhost:3001,http://127.0.0.1:3001` | 允许的跨域来源，逗号分隔 |

## 目录结构

```
backend/
  main.py        # FastAPI 入口
  routes.py      # API 路由
  models.py      # SQLAlchemy 模型
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
