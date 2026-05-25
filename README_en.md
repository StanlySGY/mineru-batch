# MinerU Batch

<div align="center">

**Batch PDF / document to Markdown preprocessing for easy-dataset**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

English | [中文](./README.md)

</div>

MinerU Batch converts large batches of PDFs, images, and Office documents into Markdown, with a primary focus on making easy-dataset imports faster, smaller, and easier to organize.

## Use Cases

- Preprocess large PDF collections into lightweight Markdown for easy-dataset.
- Split oversized Markdown files to stay below easy-dataset import limits.
- Preserve the original folder structure for dataset organization.
- Dispatch parsing jobs across multiple MinerU API nodes for higher throughput.
- Keep full images / json / md bundle outputs for RAG knowledge base workflows when needed.

## Core Capabilities

- **easy-dataset export**: Export a Markdown-only ZIP and filter images, json, zip, and other intermediate artifacts.
- **Large file splitting**: Split each Markdown file at 45MB by default to stay below the roughly 50MB easy-dataset import limit.
- **Folder batch upload**: Drag and drop folders, auto-detect supported files, and preserve relative paths.
- **Parse presets**: Select easy-dataset / Academic / Plain Text / Scanned OCR presets during upload.
- **Multi-node load balancing**: Configure multiple MinerU service nodes and distribute tasks with Round-Robin scheduling.
- **Queue and realtime status**: Async queue, concurrency control, SSE updates, and browser notifications.
- **Preview and edit**: Markdown rendering, source mode, split view, full-text search, and saved content edits.
- **Batch operations**: Retry, delete, convert, download, clean storage, inspect logs, and review quality metrics.

## Online Demo

[Open the frontend demo](https://mineru-batch.vercel.app/)

The Vercel deployment is a static frontend preview only. It does not include backend APIs, file upload, MinerU calls, or task processing. Deploy the full service with Docker, Make, or the offline package to use parsing and downloads.

## Screenshots

<div align="center">
<img src="docs/dashboard.png" width="80%" alt="Dashboard Overview" />
<p><em>Dashboard: task metrics, queue status, trend charts, and node health</em></p>
</div>

<div align="center">
<img src="docs/upload.png" width="80%" alt="Upload and Parse" />
<p><em>Upload: drag folders, select the easy-dataset preset, and upload in concurrent batches</em></p>
</div>

<div align="center">
<img src="docs/preview.png" width="80%" alt="Markdown Preview" />
<p><em>Markdown Preview: rendered / source / split view with full-text search</em></p>
</div>

## easy-dataset Batch Import Workflow

### Recommended Flow

```bash
# 1. Start MinerU Batch
make prod

# 2. Configure MinerU API nodes in Settings
# Add multiple nodes if you need higher batch throughput

# 3. Select the easy-dataset parse preset on the Upload page
# This preset outputs lightweight Markdown and disables images, intermediate JSON, and model outputs

# 4. Drag and drop a PDF folder
# The system preserves relative folder structure

# 5. After tasks complete, select them on the task list and click "easy-dataset package"
# Download the Markdown-only ZIP and import it into easy-dataset
```

### Export Rules

- Export only `.md` files and filter images / json / zip intermediate artifacts.
- Preserve upload-time relative directory structure.
- Convert `xxx.pdf` to `xxx.md` inside the ZIP.
- Split a single Markdown file into `xxx.part01.md`, `xxx.part02.md` at 45MB by default, preferring heading and paragraph boundaries.
- Include `manifest.json` with exported tasks, part names, Markdown sizes, and skipped items.
- Estimate before download: `GET /api/tasks/batch/estimate-markdown?ids=1,2,3&max_part_mb=45`.
- Download API: `GET /api/tasks/batch/download-markdown?ids=1,2,3&max_part_mb=45`.

## Quick Start

### Option 1: Make

```bash
make prod
```

Visit: http://localhost:8900

This is suitable for local trials or direct server execution. The host needs LibreOffice for Word / PPT / Excel to PDF conversion.

### Option 2: Docker Compose

```bash
cp .env.example .env
# Adjust APP_PORT, ADMIN_API_KEY, and ALLOW_PRIVATE_ENDPOINTS as needed
docker compose --env-file .env up -d
```

Visit: http://localhost:8900

Data is persisted in the Docker volume `data`. For production, set `ADMIN_API_KEY`; for public deployments, set `ALLOW_PRIVATE_ENDPOINTS=false`.

### Option 3: Development Mode

```bash
make dev
```

- Frontend: http://localhost:3001
- Backend: http://localhost:8900/docs

### Offline Deployment

```bash
bash prepare-offline.sh
# Copy generated mineru-batch-offline-*.tar.gz to the target machine, extract it, then run deploy.sh
```

Offline upgrade:

```bash
bash update-offline.sh mineru-batch-offline-vX.Y.Z.tar.gz
```

## Deployment Guide

| Scenario | Recommended Method | Notes |
|----------|--------------------|-------|
| Local trial | `make prod` | Fastest way to run the full frontend and backend |
| Long-running server | Docker Compose | Recommended production deployment with persistence and easier upgrades |
| Offline private environment | Offline package | Suitable when the target machine cannot access image registries |
| UI preview only | Vercel | Static frontend demo only, no backend API |
| Public production | Docker Compose + Nginx | Configure HTTPS, upload limits, admin key, and CORS |

## Feature Details

### Dashboard

- Task metric cards: total, pending, processing, completed, and failed.
- Success rate, failure rate, average duration, and disk usage.
- 7-day completion / failure trend chart.
- File type distribution, failure categories, batch progress, and node health.

### Upload and Parse

- Drag and drop or click to upload files and folders.
- Auto-detect Word / PPT / Excel and optionally convert them to PDF.
- Realtime upload progress with speed and estimated remaining time.
- easy-dataset / Academic / Plain Text / Scanned OCR parse presets.
- Per-batch MinerU node selection, defaulting to all enabled nodes.

### Task Management

- Search, filter, and paginate tasks.
- Detail drawer with timeline, MinerU parameters, and error stack.
- Batch retry, delete, convert, download, and easy-dataset package export.
- Retry with the original node, another enabled node, or a custom URL.
- Mobile layout automatically switches to cards.

### Preview and Edit

- Async Markdown rendering with code highlighting.
- Source / rendered / split view modes.
- Full-text search, match highlighting, and previous / next navigation.
- Save edited Markdown content.

### Logs and Operations

- Group logs by task.
- Inspect raw MinerU container logs.
- Clean upload files, output files, converted files, and database storage.
- Review quality reports, failure categories, queue status, and node health.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_MODE` | — | Set to `1` to skip static file serving |
| `CORS_ORIGINS` | — | Allowed CORS origins, separated by commas |
| `UPLOAD_DIR` | `./uploads` | Upload file directory |
| `OUTPUT_DIR` | `./outputs` | Output file directory |
| `CONVERT_DIR` | `./converted` | Document conversion directory |
| `DATABASE_URL` | `sqlite:///./mineru_batch.db` | Database connection URL, supports SQLite and PostgreSQL |
| `ADMIN_API_KEY` | — | Admin API key; when set, delete, retry, cleanup, and settings updates require authentication |
| `ALLOW_PRIVATE_ENDPOINTS` | `true` | Whether MinerU endpoints may use private / internal addresses; set to `false` for public production |
| `TAG` | `v0.1.0` | Docker Compose image tag |
| `APP_PORT` | `8900` | Docker Compose published port |
| `TZ` | `Asia/Shanghai` | Container timezone |
| `VITE_API_BASE_URL` | `/api` | Backend API base URL for split frontend / backend deployments |

## Production Security Checklist

- Set a strong random `ADMIN_API_KEY` to protect admin operations.
- Set `ALLOW_PRIVATE_ENDPOINTS=false` for public deployments to reduce SSRF exposure.
- Configure `CORS_ORIGINS` to allow only trusted frontend origins.
- Configure HTTPS and upload size limits through Nginx or your gateway.
- Do not expose internal MinerU nodes directly to the public internet.
- Regularly clean completed task source files with the storage cleanup feature.
- Check logs before sharing them externally because they may contain internal URLs, API keys, or file content.

## Directory Structure

```text
mineru-batch/
├── backend/
│   ├── main.py              # FastAPI entry + frontend static serving
│   ├── routes.py            # API routes
│   ├── models.py            # SQLAlchemy models
│   ├── services/            # Business service layer
│   ├── requirements.txt
│   └── tests/               # pytest test suite
├── frontend/
│   ├── src/
│   │   ├── views/           # Page components
│   │   ├── stores/          # Config state management
│   │   ├── utils/           # Utilities
│   │   └── api.ts           # API wrapper
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── prepare-offline.sh
├── update-offline.sh
├── Makefile
└── start.sh
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + TypeScript + Element Plus + ECharts + Marked |
| Backend | FastAPI + SQLAlchemy + SQLite / PostgreSQL |
| Document Conversion | LibreOffice headless |
| Deployment | Docker / Make / uvicorn |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload files and create tasks |
| `GET` | `/api/tasks` | Task list with pagination and filters |
| `GET` | `/api/tasks/events` | Realtime task status SSE stream |
| `GET` | `/api/tasks/since` | Sync task updates missed during disconnects |
| `GET` | `/api/tasks/{id}` | Task details |
| `PUT` | `/api/tasks/{id}` | Update task parse parameters |
| `DELETE` | `/api/tasks/{id}` | Delete task |
| `POST` | `/api/tasks/{id}/retry` | Retry task |
| `POST` | `/api/tasks/{id}/cancel` | Cancel task |
| `POST` | `/api/tasks/{id}/convert` | Convert document to PDF |
| `GET` | `/api/tasks/{id}/preview` | Preview result |
| `PUT` | `/api/tasks/{id}/content` | Save edited result content |
| `GET` | `/api/tasks/{id}/download` | Download result |
| `DELETE` | `/api/tasks/batch` | Batch delete tasks |
| `POST` | `/api/tasks/batch/retry` | Batch retry tasks |
| `POST` | `/api/tasks/batch/convert` | Batch convert documents to PDF |
| `GET` | `/api/tasks/batch/download` | Batch download results |
| `GET` | `/api/tasks/batch/download-markdown` | Export easy-dataset Markdown-only ZIP |
| `GET` | `/api/stats` | Statistics overview |
| `GET` | `/api/stats/trend` | Trend data |
| `GET` | `/api/stats/filetypes` | File type distribution |
| `GET` | `/api/reports/quality` | Quality report |
| `GET` | `/api/reports/failures` | Failure categories |
| `GET` | `/api/reports/batches` | Batch progress report |
| `GET` | `/api/nodes/health` | MinerU node health |
| `GET` | `/api/settings` | Read server settings |
| `PUT` | `/api/settings` | Save server settings |
| `GET` | `/api/security/status` | Security configuration status |
| `GET` | `/api/queue/status` | Task queue status |
| `GET` | `/api/concurrency` | Read worker concurrency |
| `PUT` | `/api/concurrency` | Set worker concurrency |
| `POST` | `/api/test-connection` | Test MinerU node connection |
| `GET` | `/api/logs` | Log list |
| `GET` | `/api/logs/grouped` | Grouped logs |
| `DELETE` | `/api/logs` | Clear logs |
| `GET` | `/api/logs/mineru-container` | Raw MinerU container logs |
| `GET` | `/api/storage` | Storage usage |
| `POST` | `/api/storage/clean` | Clean selected storage targets |
| `POST` | `/api/storage/clean-sources` | Clean completed task source files |

Full API documentation: http://localhost:8900/docs

## RAG Knowledge Base Extension

Besides easy-dataset, MinerU Batch can preserve complete MinerU bundle outputs for RAG knowledge base workflows.

Recommended configuration:

| Scenario | parse_method | formula_enable | table_enable | return_images |
|----------|--------------|----------------|--------------|---------------|
| Technical docs | auto | true | true | true |
| Academic papers | auto | true | true | true |
| Plain text reports | txt | false | false | false |
| Scanned PDFs | ocr | true | true | true |

Webhook integration can push parsed results after task completion, which works well with Dify, FastGPT, LangChain, and similar pipelines.

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

## Hardware and Dependencies

MinerU Batch itself is a lightweight scheduler. Heavy parsing work happens on your configured MinerU API nodes. A 1-core 2GB lightweight server is usually enough for the scheduler.

- Docker deployment: LibreOffice is already included in the image.
- `make prod`: LibreOffice must be installed on the host.

```bash
# Ubuntu / Debian
sudo apt install libreoffice

# CentOS / RHEL
sudo yum install libreoffice
```

## FAQ

**Q: Why cannot the Vercel demo upload files?**

A: The Vercel version is a static frontend preview only. Full upload, parsing, and download capabilities require a deployed backend service.

**Q: Uploading a large file returns 413 Request Entity Too Large.**

A: If you use Nginx as a reverse proxy, increase the upload limit:

```nginx
client_max_body_size 500m;
```

**Q: DOCX / PPT / Excel to PDF conversion fails.**

A: Check whether LibreOffice is installed. Docker deployments include it by default; `make prod` requires host-level installation.

**Q: How do I configure multiple MinerU nodes?**

A: Add and enable nodes in the Settings page. During upload, you can select which nodes the batch should use; tasks are distributed automatically.

**Q: Why does the easy-dataset package not include images or JSON?**

A: This is expected. The easy-dataset package exports Markdown only to reduce import size. Use normal batch download if you need complete artifacts.

**Q: Is PostgreSQL supported?**

A: Yes. Set `DATABASE_URL=postgresql://user:password@host:5432/mineru_batch`.

## License

MIT
