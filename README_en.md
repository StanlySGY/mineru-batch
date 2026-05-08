# MinerU Batch

<div align="center">

**Batch PDF / Document Parsing Tool powered by MinerU API**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

English | [中文](./README.md)

</div>

---

## Screenshots

<!-- Place screenshots in docs/ directory -->
<div align="center">
<img src="docs/dashboard.png" width="80%" alt="Dashboard Overview" />
<p><em>Dashboard: Task statistics, trend charts, file type distribution</em></p>
</div>

<div align="center">
<img src="docs/upload.png" width="80%" alt="Upload & Parse" />
<p><em>Upload: Drag & drop folders, batch concurrent upload, real-time progress</em></p>
</div>

<div align="center">
<img src="docs/preview.png" width="80%" alt="Markdown Preview" />
<p><em>Markdown Preview: Render/source toggle, full-text search highlighting</em></p>
</div>

## Features

```mermaid
graph TB
    User[User Browser] -->|Upload| LB[MinerU Batch Scheduler]
    LB -->|Round-Robin| N1[MinerU Node 1]
    LB -->|Round-Robin| N2[MinerU Node 2]
    LB -->|Round-Robin| N3[MinerU Node 3]
    N1 -->|Result| LB
    N2 -->|Result| LB
    N3 -->|Result| LB
    LB -->|SSE Push| User
    LB -->|Store| DB[(SQLite)]
    LB -->|Files| FS[Filesystem]
    LB -->|Webhook| EXT[External Service]
```

**Core Capabilities:**
- Multi-node load balancing (Round-Robin)
- Async task queue (concurrency control)
- ZIP stream auto-extraction (Bundle output preservation)
- Webhook auto-push (pipeline integration)

## Features

- **Batch Upload & Parse** — Drag & drop PDF / Images / Word / PPT / Excel, auto-queue processing
- **Folder Drag & Drop** — Directly drag folders to upload area, auto-detect and preserve directory structure
- **Multi-node Load Balancing** — Configure multiple MinerU service nodes, round-robin task distribution
- **RAG Bundle Output** — Support saving images / json / md complete artifacts, perfect for RAG knowledge base building
- **Real-time Status Push** — SSE real-time task status push, browser desktop notification support
- **Markdown Preview** — Built-in rendered preview, source code toggle, full-text search highlighting, async rendering
- **Task Management** — Batch retry / delete / convert / download, CSV export, one-click apply task parameters
- **Config Presets** — Save / load commonly used configurations, one-click switch
- **Trend Charts** — Dashboard displays 7-day trends, file type distribution
- **Storage Cleanup** — One-click cleanup of completed task source files, free disk space
- **Mobile Responsive** — Responsive layout, sidebar auto-collapse

## Quick Start

### Option 1: Make (Recommended)

```bash
# Production mode — auto-build frontend + start service
make prod
```

Visit http://localhost:8900

### Option 2: Docker

```bash
docker compose up -d
```

Data persisted in Docker volume `data`.

### Option 3: Development Mode

```bash
make dev
```

Frontend and backend run separately with hot reload:
- Frontend: http://localhost:3001
- Backend: http://localhost:8900/docs

## Feature Details

### Dashboard Overview

- Task statistics cards (Total / Pending / Processing / Completed / Failed)
- Success rate, average duration, disk usage
- 7-day completion/failure trend chart
- File type distribution pie chart

### Upload & Parse

- Drag & drop or click to upload, batch support, direct folder drag & drop auto-detection
- Auto-detect document format (Word/PPT/Excel), optional auto-convert to PDF
- Real-time upload progress display (speed + estimated remaining time)
- Config preset quick switch

### Task Management

- Task list supports search, status filter, sort
- Click task row to view detail drawer (timeline, MinerU parameters, error stack)
- Batch operations: retry / delete / convert / download
- One-click apply task parameters, quickly reproduce parse config
- Mobile auto-switch to card layout

### Preview & Search

- Markdown async rendered preview, code block syntax highlighting
- Source / rendered mode toggle
- Full-text search, match highlighting + up/down navigation

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_MODE` | — | Set to `1` to skip static file serving |
| `CORS_ORIGINS` | — | Allowed CORS origins (comma-separated) |
| `UPLOAD_DIR` | `./uploads` | Upload file directory |
| `OUTPUT_DIR` | `./outputs` | Output file directory |
| `CONVERT_DIR` | `./converted` | Document conversion directory |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | Database connection URL |

## Directory Structure

```
mineru-batch/
├── backend/
│   ├── main.py          # FastAPI entry + frontend static serving
│   ├── routes.py        # API routes (upload, tasks, logs, stats)
│   ├── models.py        # SQLAlchemy models
│   ├── requirements.txt
│   └── tests/           # pytest test suite
├── frontend/
│   ├── src/
│   │   ├── views/       # Page components
│   │   ├── stores/      # Config state management
│   │   ├── utils/       # Utility functions
│   │   └── api.ts       # API wrapper
│   ├── public/
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── start.sh
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + TypeScript + Element Plus + ECharts |
| Backend | FastAPI + SQLAlchemy + SQLite |
| Document Conversion | LibreOffice (headless) |
| Deployment | Docker / Make / uvicorn |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload files and create tasks |
| `GET` | `/api/tasks` | Task list (paginated, filtered) |
| `GET` | `/api/tasks/{id}` | Task details |
| `POST` | `/api/tasks/{id}/retry` | Retry task |
| `POST` | `/api/tasks/{id}/cancel` | Cancel task |
| `DELETE` | `/api/tasks/{id}` | Delete task |
| `GET` | `/api/tasks/{id}/preview` | Preview result |
| `GET` | `/api/tasks/{id}/download` | Download result |
| `GET` | `/api/stats` | Statistics overview |
| `GET` | `/api/stats/trend` | Trend data |
| `GET` | `/api/stats/filetypes` | File type distribution |
| `GET` | `/api/logs` | Log list |
| `GET` | `/api/storage` | Storage usage |
| `POST` | `/api/storage/clean` | Clean specified directory |
| `POST` | `/api/storage/clean-sources` | Clean completed task source files |

Full API documentation: http://localhost:8900/docs

## RAG Knowledge Base Best Practices

The core value of MinerU Batch is providing high-quality corpus for LLM knowledge bases.

### Scenario: Batch Process Technical Documents

```bash
# 1. Prepare document directory
mkdir -p ~/rag-source-docs
# Place PDF/Word/PPT files

# 2. Start MinerU Batch
make prod

# 3. Configure MinerU nodes in Settings page

# 4. Drag entire folder to upload area
# System auto-preserves directory structure

# 5. Wait for parsing, download Bundle
# Bundle contains: output.md + images/ + content_list.json
```

### Recommended Config

| Scenario | parse_method | formula_enable | table_enable | return_images |
|----------|--------------|----------------|--------------|---------------|
| Technical Docs | auto | true | true | true |
| Academic Papers | auto | true | true | true |
| Plain Text Reports | txt | false | false | false |
| Scanned PDFs | ocr | true | true | true |

### Webhook Auto-Push

Configure Webhook URL to auto-push results on task completion:

```json
{
  "task_id": 42,
  "filename": "paper.pdf",
  "status": "completed",
  "output_format": "md",
  "content": "...parsed Markdown content...",
  "images": ["img1.png", "img2.png"]
}
```

Compatible with: Dify, FastGPT, LangChain and other RAG frameworks.

## Development

```bash
# Install backend dependencies
pip install -r backend/requirements.txt

# Install frontend dependencies
cd frontend && npm install

# Run tests
make test

# Build frontend
make build

# Clean
make clean
```

## License

MIT
