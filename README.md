# MinerU Batch

<div align="center">

**面向 easy-dataset 的批量 PDF / 文档转 Markdown 预处理工具**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](./README_en.md) | 中文

</div>

MinerU Batch 用于把大量 PDF、图片和 Office 文档批量解析为 Markdown，重点解决 easy-dataset 在大文件上传、批量导入和目录结构维护上的使用成本问题。

## 适用场景

- 将大批量 PDF 预处理为 easy-dataset 可导入的轻量 Markdown。
- 将超过 easy-dataset 单文件限制的大 Markdown 自动拆分为多个分片文件。
- 保留原始文件夹目录结构，便于按资料来源组织数据集。
- 批量调用多个 MinerU API 节点，提高解析吞吐。
- 兼容 RAG 知识库构建，保留 images / json / md 等完整 Bundle 产物。

## 核心能力

- **easy-dataset 专用导出**：一键导出 Markdown-only ZIP，自动过滤 images、json、zip 等中间产物。
- **大文件分片**：单个 Markdown 超过默认 45MB 时自动拆分，避免超过 easy-dataset 导入限制。
- **文件夹批量上传**：支持拖拽文件夹，自动识别文件并保留相对路径。
- **解析场景预设**：上传时可选择 easy-dataset / 学术论文 / 纯文本 / 扫描件 OCR 等预设。
- **多节点负载均衡**：配置多个 MinerU 服务节点，按 Round-Robin 分配解析任务。
- **任务队列与实时状态**：异步队列、并发控制、SSE 实时推送、浏览器通知。
- **结果预览与编辑**：Markdown 渲染、源码切换、双栏对照、全文搜索、结果内容保存。
- **批量运维**：批量重试、删除、转换、下载、存储清理、日志排查、质量统计。

## 在线演示

[在线预览前端界面](https://mineru-batch.vercel.app/)

在线演示部署在 Vercel，仅用于查看 UI 与交互流程，不包含后端 API、文件上传、MinerU 调用和任务处理能力。完整功能请使用 Docker、Make 或离线包部署后访问本地服务。

## 界面预览

<div align="center">
<img src="docs/dashboard.png" width="80%" alt="Dashboard 概览" />
<p><em>Dashboard：任务统计、队列状态、趋势图表、节点健康</em></p>
</div>

<div align="center">
<img src="docs/upload.png" width="80%" alt="上传解析" />
<p><em>上传解析：拖拽文件夹、选择 easy-dataset 预设、分批并发上传</em></p>
</div>

<div align="center">
<img src="docs/preview.png" width="80%" alt="Markdown 预览" />
<p><em>Markdown 预览：渲染 / 源码 / 双栏对照、全文搜索高亮</em></p>
</div>

## easy-dataset 批量导入工作流

### 推荐流程

```bash
# 1. 启动 MinerU Batch
make prod

# 2. 在设置页配置 MinerU API 节点
# 可配置多个节点提升批量处理吞吐

# 3. 上传页默认使用 easy-dataset 解析场景
# 该默认预设输出轻量 Markdown，并关闭图片、中间 JSON、模型输出等大体积产物

# 4. 拖拽 PDF 文件夹上传
# 系统会保留相对目录结构

# 5. 任务完成后，在任务列表勾选任务并点击“导出 Markdown”
# 如果从批次入口进入任务页，可直接点击“导出本批次 Markdown”
# 解压 ZIP 后，将 .md 文件直接拖入 easy-dataset
```

### 导出规则

- 仅导出 `.md` 文件，自动过滤 images / json / zip 等中间产物。
- 保留上传时的相对目录结构，便于按原资料目录组织数据集。
- `xxx.pdf` 自动导出为 `xxx.md`。
- 单个 Markdown 默认按 45MB 拆分为 `xxx.part01.md`、`xxx.part02.md`，优先按标题和段落边界切分。
- ZIP 默认只包含 Markdown 文件，解压后可直接拖入 easy-dataset。
- 下载 API：`GET /api/tasks/batch/download-markdown?ids=1,2,3`。

## 快速启动

### 方式一：Make

```bash
make prod
```

访问：http://localhost:8900

适合本地试用或直接在服务器上运行。宿主机需要安装 LibreOffice 才能启用 Word / PPT / Excel 转 PDF。

### 方式二：Docker Compose

```bash
cp .env.example .env
# 按需修改 APP_PORT、ADMIN_API_KEY、ALLOW_PRIVATE_ENDPOINTS
docker compose --env-file .env up -d
```

访问：http://localhost:8900

数据默认持久化在 Docker volume `data` 中。生产部署建议设置 `ADMIN_API_KEY`，公网环境建议设置 `ALLOW_PRIVATE_ENDPOINTS=false`。

### 方式三：开发模式

```bash
make dev
```

- 前端：http://localhost:3001
- 后端：http://localhost:8900/docs

### 离线部署

```bash
bash prepare-offline.sh
# 将生成的 mineru-batch-offline-*.tar.gz 拷贝到目标机器后解压并执行 deploy.sh
```

离线升级：

```bash
bash update-offline.sh mineru-batch-offline-vX.Y.Z.tar.gz
```

## 部署方式选择

| 场景 | 推荐方式 | 说明 |
|------|----------|------|
| 本地快速体验 | `make prod` | 最少步骤启动完整前后端 |
| 服务器长期运行 | Docker Compose | 推荐生产方式，便于持久化和升级 |
| 内网离线环境 | 离线包 | 适合无法直接访问镜像仓库的私有化环境 |
| 只查看界面 | Vercel | 仅静态前端演示，不包含后端 API |
| 公网生产部署 | Docker Compose + Nginx | 建议配置 HTTPS、上传大小限制、管理员密钥和 CORS |

## 功能说明

### Dashboard

- 任务统计卡片：总数、等待、处理中、完成、失败。
- 成功率、失败率、平均耗时、磁盘占用。
- 近 7 天完成 / 失败趋势图。
- 文件类型分布、失败原因分类、批次进度、节点健康。

### 上传解析

- 拖拽或点击上传，支持文件夹批量上传。
- 自动检测 Word / PPT / Excel，可选自动转 PDF。
- 上传进度实时显示，包含速度和预计剩余时间。
- easy-dataset / 学术论文 / 纯文本 / 扫描件 OCR 场景预设。
- 每批上传可独立选择 MinerU 节点，默认使用所有已启用节点。

### 任务管理

- 任务列表支持搜索、状态筛选和分页。
- 任务详情抽屉展示时间线、MinerU 参数和错误堆栈。
- 批量重试、删除、转换、下载和 easy-dataset Markdown 导出，批次视图可一键重试失败任务。
- 重试时可保持原节点、切换到其他节点或填写自定义 URL。
- 移动端自动切换为卡片布局。

### 预览与编辑

- Markdown 异步渲染预览，支持代码块语法高亮。
- 源码 / 渲染 / 双栏对照模式切换。
- 全文搜索、匹配高亮、上下跳转。
- 可保存编辑后的 Markdown 内容。

### 日志与运维

- 按任务分组查看解析日志。
- 查看 MinerU 容器原始日志。
- 清理上传文件、输出文件、转换文件和数据库占用。
- 质量报告、失败原因分类、队列状态和节点健康巡检。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEV_MODE` | — | 设为 `1` 跳过静态文件服务 |
| `CORS_ORIGINS` | — | 允许的跨域来源，多个来源用逗号分隔 |
| `UPLOAD_DIR` | `./uploads` | 上传文件目录 |
| `OUTPUT_DIR` | `./outputs` | 输出文件目录 |
| `CONVERT_DIR` | `./converted` | 文档转换目录 |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | 数据库连接 URL，支持 SQLite 和 PostgreSQL |
| `ADMIN_API_KEY` | — | 管理接口访问密钥；设置后删除、重试、清理、保存配置等操作需认证 |
| `ALLOW_PRIVATE_ENDPOINTS` | `true` | 是否允许 MinerU 节点使用私有 / 内网地址；公网生产建议设为 `false` |
| `TAG` | `v0.1.0` | Docker Compose 使用的镜像标签 |
| `APP_PORT` | `8900` | Docker Compose 暴露端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |
| `VITE_API_BASE_URL` | `/api` | 前后端分离部署时的后端 API 地址 |

## 生产安全清单

- 设置强随机 `ADMIN_API_KEY`，避免管理接口裸露。
- 公网部署时将 `ALLOW_PRIVATE_ENDPOINTS=false`，降低 SSRF 风险。
- 配置 `CORS_ORIGINS`，只允许可信前端域名访问 API。
- 通过 Nginx / 网关配置 HTTPS 和上传大小限制。
- 不要把内部 MinerU 节点直接暴露到公网。
- 定期使用存储清理功能删除已完成任务的源文件。
- 对外分享日志前确认其中不包含内部 URL、API Key 或文件内容。

## 目录结构

```text
mineru-batch/
├── backend/
│   ├── main.py              # FastAPI 入口 + 前端静态服务
│   ├── routes.py            # API 路由
│   ├── models.py            # SQLAlchemy 模型
│   ├── services/            # 业务逻辑服务层
│   ├── requirements.txt
│   └── tests/               # pytest 测试套件
├── frontend/
│   ├── src/
│   │   ├── views/           # 页面组件
│   │   ├── stores/          # 配置状态管理
│   │   ├── utils/           # 工具函数
│   │   └── api.ts           # API 封装
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── prepare-offline.sh
├── update-offline.sh
├── Makefile
└── start.sh
```

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts + Marked |
| 后端 | FastAPI + SQLAlchemy + SQLite / PostgreSQL |
| 文档转换 | LibreOffice headless |
| 部署 | Docker / Make / uvicorn |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传文件并创建任务 |
| `GET` | `/api/tasks` | 任务列表，支持分页和筛选 |
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
| `GET` | `/api/reports/failures` | 失败原因分类 |
| `GET` | `/api/reports/batches` | 批次进度报告 |
| `GET` | `/api/nodes/health` | MinerU 节点健康状态 |
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

完整 API 文档：http://localhost:8900/docs

## RAG 知识库扩展用法

除 easy-dataset 外，也可以保留 MinerU 的完整 Bundle 产物用于 RAG 知识库构建。

推荐配置：

| 场景 | parse_method | formula_enable | table_enable | return_images |
|------|--------------|----------------|--------------|---------------|
| 技术文档 | auto | true | true | true |
| 学术论文 | auto | true | true | true |
| 纯文本报告 | txt | false | false | false |
| 扫描件 OCR | ocr | true | true | true |

Webhook 可在任务完成后推送解析结果，适用于 Dify、FastGPT、LangChain 等流水线集成。

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

## 硬件与依赖

MinerU Batch 本身是轻量级调度平台，重负载发生在已配置的 MinerU API 节点上。通常 1 核 2G 的轻量云服务器即可运行调度端。

- Docker 部署：镜像内已包含 LibreOffice。
- `make prod` 部署：宿主机需要安装 LibreOffice。

```bash
# Ubuntu / Debian
sudo apt install libreoffice

# CentOS / RHEL
sudo yum install libreoffice
```

## FAQ

**Q: Vercel 在线演示为什么不能上传文件？**

A: Vercel 版本仅部署静态前端，不包含后端 API。完整上传、解析和下载能力需要本地或服务器部署后端服务。

**Q: 上传大文件提示 413 Request Entity Too Large？**

A: 如果使用 Nginx 反向代理，需要调整上传大小限制：

```nginx
client_max_body_size 500m;
```

**Q: DOCX / PPT / Excel 自动转 PDF 失败？**

A: 检查宿主机或容器中是否安装 LibreOffice。Docker 部署默认已包含，`make prod` 需要宿主机自行安装。

**Q: 如何配置多个 MinerU 节点？**

A: 在“系统设置”页面添加多个节点并启用，上传时可选择本批任务使用的节点，系统会自动轮询分配任务。

**Q: Markdown 导出里为什么没有图片和 JSON？**

A: 这是预期行为。该导出只保留可直接导入 easy-dataset 的 Markdown，用于降低导入体积；如需完整产物，请使用普通批量下载。

**Q: 支持 PostgreSQL 吗？**

A: 支持。设置 `DATABASE_URL=postgresql://user:password@host:5432/mineru_batch` 即可。

## 许可证

MIT
