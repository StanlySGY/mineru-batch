# MinerU Batch

<p align="center">
  <strong>批量 PDF / 文档解析工具</strong>
  <br>
  基于 MinerU API，支持多节点负载均衡、任务队列、实时进度推送
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/node-18+-green.svg" alt="Node.js 18+">
  <img src="https://img.shields.io/badge/vue-3.5-brightgreen.svg" alt="Vue 3.5">
  <img src="https://img.shields.io/badge/fastapi-0.110+-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
</p>

---

## 功能特性

| 分类 | 功能 |
|------|------|
| **批量处理** | 多文件上传、任务队列、并发控制 (1-20)、自动重试 |
| **文件支持** | PDF、图片 (PNG/JPG/BMP/TIFF/WebP)、Word、PPT、Excel |
| **多节点** | MinerU 服务节点管理、轮询负载均衡、连接测试 |
| **任务管理** | 状态筛选、文件名搜索、批量操作 (删除/重试/转换/下载) |
| **结果预览** | Markdown 渲染、源码切换、全文搜索、代码高亮 |
| **数据统计** | Dashboard 概览、7 天趋势图、文件类型分布、成功率/耗时 |
| **配置管理** | 配置预设、导入/导出 JSON、一键恢复默认 |
| **实时推送** | SSE 任务状态推送、浏览器桌面通知 |
| **存储管理** | 磁盘占用统计、按目录清理 |

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

## Docker 部署

```bash
docker compose up -d
```

访问 http://localhost:8900。数据持久化在 Docker volume `data` 中。

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
| `UPLOAD_DIR` | `./uploads` | 上传文件目录 |
| `OUTPUT_DIR` | `./outputs` | 输出文件目录 |
| `CONVERT_DIR` | `./converted` | 文档转换目录 |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | 数据库连接 URL |

## 目录结构

```
mineru-batch/
├── backend/
│   ├── main.py          # FastAPI 入口 + 前端静态服务
│   ├── routes.py        # API 路由 (任务、日志、存储、统计)
│   ├── models.py        # SQLAlchemy 模型 (FileTask, ProcessLog)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/       # 页面组件 (Dashboard, Upload, Tasks, Logs, Settings)
│   │   ├── layout/      # 布局组件 (侧边栏 + 顶栏)
│   │   ├── stores/      # 配置状态管理 (localStorage 持久化)
│   │   ├── utils/       # 工具函数 (文件类型、错误翻译、格式化)
│   │   └── api.ts       # Axios 封装 + SSE 连接
│   └── vite.config.ts
├── uploads/             # 上传文件存储
├── outputs/             # 解析结果输出
├── converted/           # 文档转 PDF 中间文件
├── Makefile
├── docker-compose.yml
└── start.sh             # 开发环境一键启动脚本
```

## API 文档

启动后端后访问 http://localhost:8900/docs 查看 Swagger UI 交互式文档。

主要接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传文件并创建任务 |
| `GET` | `/api/tasks` | 任务列表 (支持分页、状态筛选、文件名搜索) |
| `GET` | `/api/tasks/events` | SSE 任务状态推送流 |
| `POST` | `/api/tasks/{id}/retry` | 重试任务 |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `GET` | `/api/tasks/{id}/preview` | 预览解析结果 |
| `GET` | `/api/tasks/{id}/download` | 下载解析结果 |
| `GET` | `/api/stats` | 任务统计概览 |
| `GET` | `/api/stats/trend` | 完成/失败趋势 |
| `GET` | `/api/stats/filetypes` | 文件类型分布 |

## 技术栈

**后端**
- FastAPI + Uvicorn
- SQLAlchemy + SQLite (WAL 模式)
- httpx (HTTP 客户端)
- aiofiles (异步文件 I/O)

**前端**
- Vue 3.5 + TypeScript
- Element Plus (UI 组件库)
- ECharts (数据可视化)
- Axios (HTTP 请求)
- highlight.js (代码高亮)
- marked + DOMPurify (Markdown 渲染)

## 许可证

MIT
