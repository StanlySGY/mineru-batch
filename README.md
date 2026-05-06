# MinerU Batch

<div align="center">

**批量 PDF / 文档解析工具，基于 MinerU API**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 功能特性

- **批量上传解析** — 拖拽上传 PDF / 图片 / Word / PPT / Excel，自动排队处理
- **文件夹拖拽** — 直接拖拽文件夹到上传区域，自动识别并保留目录结构
- **多节点负载均衡** — 配置多个 MinerU 服务节点，轮询分配任务
- **RAG Bundle 输出** — 支持保存 images / json / md 完整产物，适配 RAG 知识库搭建
- **实时状态推送** — SSE 实时推送任务状态，支持浏览器桌面通知
- **Markdown 预览** — 内置渲染预览，支持源码切换、全文搜索高亮、异步渲染
- **任务管理** — 批量重试 / 删除 / 转换 / 下载，CSV 导出，一键套用任务参数
- **配置预设** — 保存 / 加载常用配置，一键切换
- **趋势图表** — Dashboard 展示 7 天趋势、文件类型分布
- **存储清理** — 一键清理已完成任务原文件，释放磁盘空间
- **移动端适配** — 响应式布局，侧边栏自动收起

## 快速启动

### 方式一：Make（推荐）

```bash
# 生产模式 — 自动构建前端 + 启动服务
make prod
```

访问 http://localhost:8900

### 方式二：Docker

```bash
docker compose up -d
```

数据持久化在 Docker volume `data` 中。

### 方式三：开发模式

```bash
make dev
```

前后端分离运行，支持热更新：
- 前端：http://localhost:3001
- 后端：http://localhost:8900/docs

## 功能说明

### Dashboard 概览

- 任务统计卡片（总数 / 等待 / 处理中 / 完成 / 失败）
- 成功率、平均耗时、磁盘占用
- 近 7 天完成/失败趋势图
- 文件类型分布饼图

### 上传解析

- 拖拽或点击上传，支持批量，可直接拖拽文件夹自动识别
- 自动检测文档格式（Word/PPT/Excel），可选自动转 PDF
- 上传进度实时显示（速度 + 预计剩余时间）
- 配置预设快速切换

### 任务管理

- 任务列表支持搜索、状态筛选、排序
- 点击任务行查看详情抽屉（时间线、MinerU 参数、错误堆栈）
- 批量操作：重试 / 删除 / 转换 / 下载
- 一键套用任务参数，快速复现解析配置
- 移动端自动切换为卡片布局

### 预览与搜索

- Markdown 异步渲染预览，代码块语法高亮
- 源码 / 渲染模式切换
- 全文搜索，匹配高亮 + 上下跳转

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEV_MODE` | — | 设为 `1` 跳过静态文件服务 |
| `CORS_ORIGINS` | — | 允许的跨域来源（逗号分隔） |
| `UPLOAD_DIR` | `./uploads` | 上传文件目录 |
| `OUTPUT_DIR` | `./outputs` | 输出文件目录 |
| `CONVERT_DIR` | `./converted` | 文档转换目录 |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | 数据库连接 URL |

## 目录结构

```
mineru-batch/
├── backend/
│   ├── main.py          # FastAPI 入口 + 前端静态服务
│   ├── routes.py        # API 路由（上传、任务、日志、统计）
│   ├── models.py        # SQLAlchemy 模型
│   ├── requirements.txt
│   └── tests/           # pytest 测试套件
├── frontend/
│   ├── src/
│   │   ├── views/       # 页面组件
│   │   ├── stores/      # 配置状态管理
│   │   ├── utils/       # 工具函数
│   │   └── api.ts       # API 封装
│   ├── public/
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── start.sh
```

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 文档转换 | LibreOffice (headless) |
| 部署 | Docker / Make / uvicorn |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传文件并创建任务 |
| `GET` | `/api/tasks` | 任务列表（分页、筛选） |
| `GET` | `/api/tasks/{id}` | 任务详情 |
| `POST` | `/api/tasks/{id}/retry` | 重试任务 |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `DELETE` | `/api/tasks/{id}` | 删除任务 |
| `GET` | `/api/tasks/{id}/preview` | 预览结果 |
| `GET` | `/api/tasks/{id}/download` | 下载结果 |
| `GET` | `/api/stats` | 统计概览 |
| `GET` | `/api/stats/trend` | 趋势数据 |
| `GET` | `/api/stats/filetypes` | 文件类型分布 |
| `GET` | `/api/logs` | 日志列表 |
| `GET` | `/api/storage` | 存储占用 |
| `POST` | `/api/storage/clean` | 清理指定目录 |
| `POST` | `/api/storage/clean-sources` | 清理已完成任务原文件 |

完整 API 文档：http://localhost:8900/docs

## 开发

```bash
# 安装后端依赖
pip install -r backend/requirements.txt

# 安装前端依赖
cd frontend && npm install

# 运行测试
make test

# 构建前端
make build

# 清理
make clean
```

## 许可证

MIT
