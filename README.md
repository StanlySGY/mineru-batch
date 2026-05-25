# MinerU Batch

<div align="center">

**🚀 批量 PDF / 文档解析工具，基于 MinerU API**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](./README_en.md) | 中文

</div>

---

## ✨ 核心特性

- 🎯 **批量上传解析** — 拖拽上传 PDF / 图片 / Word / PPT / Excel，自动排队处理
- 📁 **文件夹拖拽** — 直接拖拽文件夹到上传区域，自动识别并保留目录结构
- ⚖️ **多节点负载均衡** — 配置多个 MinerU 服务节点，轮询分配任务，充分利用计算资源
- 📦 **RAG Bundle 输出** — 支持保存 images / json / md 完整产物，适配 RAG 知识库搭建
- 🧩 **easy-dataset 导出** — 一键导出 Markdown-only ZIP，自动过滤大体积中间产物并按 50MB 限制拆分
- 🔄 **实时状态推送** — SSE 实时推送任务状态，支持浏览器桌面通知
- 📝 **Markdown 预览** — 内置渲染预览，支持源码切换、全文搜索高亮、双栏对照
- 🎛️ **任务管理** — 批量重试 / 删除 / 转换 / 下载，CSV 导出，一键套用任务参数
- 🎨 **解析场景预设** — 上传时一键切换学术论文/纯文本/扫描件 OCR 场景，自动覆盖解析参数
- 📊 **趋势图表** — Dashboard 展示 7 天趋势、文件类型分布、成功率统计
- 🧹 **存储清理** — 一键清理已完成任务原文件，释放磁盘空间
- 📱 **移动端适配** — 响应式布局，侧边栏自动收起，完美适配手机

---

## 🎨 界面预览

<div align="center">
<img src="docs/dashboard.png" width="80%" alt="Dashboard 概览" />
<p><em>📊 Dashboard：任务统计、趋势图表、文件类型分布</em></p>
</div>

<div align="center">
<img src="docs/upload.png" width="80%" alt="上传解析" />
<p><em>⬆️ 上传解析：拖拽文件夹、分批并发上传、实时进度</em></p>
</div>

<div align="center">
<img src="docs/preview.png" width="80%" alt="Markdown 预览" />
<p><em>👁️ Markdown 预览：渲染/源码切换、全文搜索高亮、双栏对照</em></p>
</div>

## 🏗️ 架构设计

<div align="center">
<img src="docs/架构图.png" width="85%" alt="系统架构设计" />
<p><em>🏗️ 系统架构：多节点负载均衡、异步任务队列、实时状态推送</em></p>
</div>

**核心能力：**
- 🔄 多节点负载均衡（Round-Robin）
- ⏳ 异步任务队列（并发可控）
- 📦 ZIP 流自动解压（Bundle 产物保留）
- 🪝 Webhook 自动推送（闭环流水线）

## 🚀 快速启动

### 🌐 在线演示

**[点击这里查看在线演示](https://mineru-batch.vercel.app/)** — 无需安装，直接在浏览器中预览完整 UI 界面

> 💡 **提示**：在线演示仅展示前端界面，需要配置后端 API 才能体验上传、解析等完整功能。

### 方式一：Make（推荐）⚡

```bash
# 生产模式 — 自动构建前端 + 启动服务
make prod
```

访问 http://localhost:8900

### 方式二：Docker

```bash
cp .env.example .env
# 按需修改 .env 中的 APP_PORT、ADMIN_API_KEY、ALLOW_PRIVATE_ENDPOINTS
docker compose --env-file .env up -d
```

数据持久化在 Docker volume `data` 中。生产部署建议设置 `ADMIN_API_KEY`，并仅在可信内网环境开启 `ALLOW_PRIVATE_ENDPOINTS=true`。

### 离线部署

```bash
bash prepare-offline.sh
# 将生成的 mineru-batch-offline-*.tar.gz 拷贝到目标机器后解压并执行 deploy.sh
```

离线升级可使用：

```bash
bash update-offline.sh mineru-batch-offline-vX.Y.Z.tar.gz
```

### 方式三：开发模式 🔧

```bash
make dev
```

前后端分离运行，支持热更新：
- 前端：http://localhost:3001
- 后端：http://localhost:8900/docs

## 📖 功能说明

### 📊 Dashboard 概览

- 📊 任务统计卡片（总数 / 等待 / 处理中 / 完成 / 失败）
- 📈 成功率、平均耗时、磁盘占用
- 📉 近 7 天完成/失败趋势图
- 🥧 文件类型分布饼图

### 📤 上传解析

- 📤 拖拽或点击上传，支持批量，可直接拖拽文件夹自动识别
- 🔍 自动检测文档格式（Word/PPT/Excel），可选自动转 PDF
- ⏱️ 上传进度实时显示（速度 + 预计剩余时间）
- 🎨 解析场景选择：easy-dataset / 学术论文 / 纯文本 / 扫描件 OCR 一键切换，自动覆盖解析参数
- 🎯 每批上传可独立勾选要使用的 MinerU 节点，默认全选已启用的节点

### 🎛️ 任务管理

- 🔎 任务列表支持搜索、状态筛选、排序
- 📋 点击任务行查看详情抽屉（时间线、MinerU 参数、错误堆栈）
- 🎛️ 批量操作：重试 / 删除 / 转换 / 下载
- 🔄 重试时可选保持原节点、切换到其他已启用节点、或填写自定义 URL
- ⚡ 一键套用任务参数，快速复现解析配置
- 📱 移动端自动切换为卡片布局

### 🔍 预览与搜索

- 📝 Markdown 异步渲染预览，代码块语法高亮
- 🔀 源码 / 渲染 / 双栏对照模式切换
- 🔍 全文搜索，匹配高亮 + 上下跳转

### 🔌 MinerU 节点日志

- 🔗 实时查看 MinerU API 调用、连接状态、超时等关键日志
- 📊 按任务分组展示，快速定位问题
- 🎯 筛选错误日志，快速排查故障
- 📋 详细的请求/响应日志，无需进入容器查看 docker logs

## ⚙️ 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEV_MODE` | — | 设为 `1` 跳过静态文件服务 |
| `CORS_ORIGINS` | — | 允许的跨域来源（逗号分隔） |
| `UPLOAD_DIR` | `./uploads` | 上传文件目录 |
| `OUTPUT_DIR` | `./outputs` | 输出文件目录 |
| `CONVERT_DIR` | `./converted` | 文档转换目录 |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | 数据库连接 URL（支持 SQLite 和 PostgreSQL） |
| `ADMIN_API_KEY` | — | 管理接口访问密钥；设置后删除、重试、清理、保存配置等操作需认证 |
| `ALLOW_PRIVATE_ENDPOINTS` | `true` | 是否允许 MinerU 节点使用私有/内网地址；生产公网部署建议设为 `false` |
| `TAG` | `v0.1.0` | Docker Compose 使用的镜像标签 |
| `APP_PORT` | `8900` | Docker Compose 暴露端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |
| `VITE_API_BASE_URL` | `/api` | 前后端分离部署时的后端 API 地址 |

## 📁 目录结构

```
mineru-batch/
├── backend/
│   ├── main.py              # FastAPI 入口 + 前端静态服务
│   ├── routes.py            # API 路由（上传、任务、日志、统计）
│   ├── models.py            # SQLAlchemy 模型
│   ├── services/            # 业务逻辑服务层
│   │   ├── upload_service.py
│   │   ├── task_service.py
│   │   ├── storage_service.py
│   │   └── ...
│   ├── requirements.txt
│   └── tests/               # pytest 测试套件（68+ 测试）
├── frontend/
│   ├── src/
│   │   ├── views/           # 页面组件（Dashboard、Upload、Tasks 等）
│   │   ├── stores/          # 配置状态管理
│   │   ├── utils/           # 工具函数
│   │   └── api.ts           # API 封装
│   ├── public/
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── prepare-offline.sh
├── update-offline.sh
├── Makefile
└── start.sh
```

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts + Marked |
| 后端 | FastAPI + SQLAlchemy + SQLite / PostgreSQL |
| 文档转换 | LibreOffice (headless) |
| 部署 | Docker / Make / uvicorn |

## 📡 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传文件并创建任务 |
| `GET` | `/api/tasks` | 任务列表（分页、筛选） |
| `GET` | `/api/tasks/events` | 任务状态 SSE 实时事件 |
| `GET` | `/api/tasks/since` | 按时间同步断连期间的任务更新 |
| `GET` | `/api/tasks/{id}` | 任务详情 |
| `PUT` | `/api/tasks/{id}` | 更新任务解析参数 |
| `DELETE` | `/api/tasks/{id}` | 删除任务 |
| `POST` | `/api/tasks/{id}/retry` | 重试任务 |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `POST` | `/api/tasks/{id}/convert` | 文档转 PDF |
| `GET` | `/api/tasks/{id}/preview` | 预览结果 |
| `PUT` | `/api/tasks/{id}/content` | 保存编辑后的结果内容 |
| `GET` | `/api/tasks/{id}/download` | 下载结果 |
| `DELETE` | `/api/tasks/batch` | 批量删除任务 |
| `POST` | `/api/tasks/batch/retry` | 批量重试任务 |
| `POST` | `/api/tasks/batch/convert` | 批量文档转 PDF |
| `GET` | `/api/tasks/batch/download` | 批量下载结果 |
| `GET` | `/api/tasks/batch/download-markdown` | 导出 easy-dataset Markdown-only ZIP |
| `GET` | `/api/stats` | 统计概览 |
| `GET` | `/api/stats/trend` | 趋势数据 |
| `GET` | `/api/stats/filetypes` | 文件类型分布 |
| `GET` | `/api/reports/quality` | 质量报告 |
| `GET` | `/api/settings` | 读取系统设置 |
| `PUT` | `/api/settings` | 保存系统设置 |
| `GET` | `/api/security/status` | 安全配置状态 |
| `GET` | `/api/queue/status` | 任务队列状态 |
| `GET` | `/api/concurrency` | 读取并发数 |
| `PUT` | `/api/concurrency` | 设置并发数 |
| `POST` | `/api/test-connection` | 测试 MinerU 节点连接 |
| `GET` | `/api/logs` | 日志列表 |
| `GET` | `/api/logs/grouped` | 分组日志 |
| `DELETE` | `/api/logs` | 清空日志 |
| `GET` | `/api/logs/mineru-container` | MinerU 容器原始日志 |
| `GET` | `/api/storage` | 存储占用 |
| `POST` | `/api/storage/clean` | 清理指定目录 |
| `POST` | `/api/storage/clean-sources` | 清理已完成任务原文件 |

**完整 API 文档：** http://localhost:8900/docs

## 🧩 easy-dataset 批量导入工作流

MinerU Batch 可作为 easy-dataset 的前置 PDF→Markdown 预处理工具，适合批量处理大 PDF、文件夹文档和混合办公文档。

### 推荐流程

```bash
# 1. 启动 MinerU Batch
make prod

# 2. 在上传页选择 easy-dataset 解析场景
# 该预设默认输出轻量 Markdown，并关闭图片、中间 JSON、模型输出等大体积产物

# 3. 拖拽 PDF 文件夹上传
# 系统会保留相对目录结构

# 4. 任务完成后，在任务列表勾选任务并点击“easy-dataset 包”
# 下载 Markdown-only ZIP，用于导入 easy-dataset
```

### 导出规则

- 仅导出 `.md`，自动过滤 images / json / zip 等中间产物。
- 保留上传时的相对目录结构，便于按原文档目录组织数据集。
- `xxx.pdf` 自动导出为 `xxx.md`。
- 单个 Markdown 默认按 45MB 拆分为 `xxx.part01.md`、`xxx.part02.md`，规避 easy-dataset 约 50MB 导入限制。
- 若需要 API 调用，可使用 `GET /api/tasks/batch/download-markdown?ids=1,2,3&max_part_mb=45`。

## 🧠 RAG 知识库最佳实践

MinerU Batch 的核心价值是为大模型知识库提供高质量语料。以下是典型工作流：

### 场景：批量处理技术文档入库

```bash
# 1. 准备文档目录
mkdir -p ~/rag-source-docs
# 将 PDF/Word/PPT 放入目录

# 2. 启动 MinerU Batch
make prod

# 3. 在设置页配置 MinerU 节点
# 填入你的 MinerU API 地址

# 4. 拖拽整个文件夹到上传区域
# 系统自动保留目录结构

# 5. 等待解析完成，下载 Bundle
# Bundle 包含: output.md + images/ + content_list.json
```

### 配置推荐

| 场景 | parse_method | formula_enable | table_enable | return_images |
|------|--------------|----------------|--------------|---------------|
| 技术文档 | auto | true | true | true |
| 学术论文 | auto | true | true | true |
| 纯文本报告 | txt | false | false | false |
| 扫描件 OCR | ocr | true | true | true |

### Webhook 自动推送

配置 Webhook URL 后，任务完成时自动推送结果：

```json
{
  "task_id": 42,
  "filename": "paper.pdf",
  "status": "completed",
  "output_format": "md",
  "content": "...解析后的Markdown内容..."
}
```

适用于：Dify、FastGPT、LangChain 等 RAG 框架的数据导入。

## 💻 开发

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

## 📋 硬件与依赖说明

> **MinerU Batch 本身是轻量级调度平台**（占用不到 200MB 内存），重负载发生在你配置的 MinerU API 节点上。因此可以轻松部署在树莓派或 1核2G 的轻量云服务器上。

- **Docker 部署**：已内置 LibreOffice，无需额外安装
- **make prod 部署**：需在宿主机安装 LibreOffice
  ```bash
  # Ubuntu/Debian
  sudo apt install libreoffice
  
  # CentOS/RHEL
  sudo yum install libreoffice
  ```

## ❓ 常见问题 (FAQ)

**Q: 上传大文件提示 413 Request Entity Too Large？** 📤

A: 如果使用了 Nginx 反向代理，需修改配置：
```nginx
client_max_body_size 500m;
```

**Q: DOCX 自动转 PDF 失败？** 📄

A: 检查系统中是否安装了 LibreOffice（见上方"硬件与依赖说明"）。

**Q: 如何配置多个 MinerU 节点实现负载均衡？** ⚖️

A: 在"系统设置"页面添加多个节点，系统会自动轮询分配任务。

**Q: 上传进度卡在某个百分比不动？** ⏳

A: 可能是网络波动导致，系统会自动重试。如果持续不动，可刷新页面重新上传。

**Q: 如何为 RAG 知识库批量处理文档？** 🧠

A: 参考上方"RAG 知识库最佳实践"章节，推荐配置 `return_images: true` 以保留图片。

**Q: 支持 PostgreSQL 吗？** 🗄️

A: 支持！设置环境变量 `DATABASE_URL=postgresql://user:password@localhost/mineru_batch` 即可。

---

## 📄 许可证

MIT

