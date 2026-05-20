# MinerU Batch 离线部署手册

## 1. 概述

MinerU Batch 是批量文档解析工具，将 PDF / 图片 / Word 等文件转换为 Markdown 格式。本文档指导在**完全离线**的环境中部署该系统。

部署架构：单机 Docker 部署，端口 `8900`，数据持久化至 Docker Volume。

---

## 2. 目标机器要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（内核 3.10+），支持 WSL2 |
| Docker | ≥ 20.10 |
| Docker Compose | ≥ 2.0（即 `docker compose` V2） |
| 磁盘空间 | ≥ 2 GB（镜像 ~800 MB + 运行数据） |
| 内存 | ≥ 2 GB（LibreOffice 转换需要内存） |
| 网络 | 仅需内网访问 MinerU API 服务 |

> 目标机器**无需** Python、Node.js、npm 等开发工具，Docker 是唯一运行时依赖。

### 2.1 检查 Docker 环境

```bash
docker --version
docker compose version
```

如果目标机器没有 Docker，需提前通过离线 rpm/deb 包安装。

---

## 3. 构建镜像（在线机器）

> **注意**：当前仓库中的 `.tar.gz` 镜像可能不是最新代码，部署前**必须重新构建**。

在可联网的开发机器上执行：

```bash
cd /path/to/mineru-batch
./docker-build.sh
```

构建过程包含：
1. `node:22-alpine` 阶段：编译 Vue 前端
2. `python:3.12-slim` 阶段：安装 Python 依赖 + LibreOffice + 拷贝后端代码 + 前端产物

构建完成后生成：
- 镜像：`mineru-batch:v0.1.0`
- 导出文件：`mineru-batch-v0.1.0.tar.gz`（约 800 MB）
- `.env` 文件自动写入 `TAG=v0.1.0`

---

## 4. 传输文件到目标机器

需要传输 2 个文件：

| 文件 | 大小 | 用途 |
|------|------|------|
| `mineru-batch-v0.1.0.tar.gz` | ~800 MB | Docker 镜像 |
| `docker-compose.yml` | < 1 KB | 容器编排配置（含版本号） |

传输方式任选：

```bash
# U盘拷贝
cp mineru-batch-v0.1.0.tar.gz docker-compose.yml /media/usb/

# SCP 传输
scp mineru-batch-v0.1.0.tar.gz docker-compose.yml user@target:/opt/mineru-batch/
```

---

## 5. 部署步骤（目标机器）

### 5.1 创建部署目录

```bash
mkdir -p /opt/mineru-batch
cd /opt/mineru-batch
```

确保 `mineru-batch-v0.1.0.tar.gz` 和 `docker-compose.yml` 均在此目录。

### 5.2 加载镜像

```bash
gunzip -c mineru-batch-v0.1.0.tar.gz | docker load
```

验证镜像已加载：

```bash
docker images mineru-batch
# 预期输出：mineru-batch  v0.1.0  ...  ~800MB
```

### 5.3 启动服务

```bash
docker compose up -d
```

验证容器运行：

```bash
docker compose ps
# 预期：app 服务状态为 Up
```

### 5.4 查看日志

```bash
docker compose logs -f
```

首次启动约 3-5 秒后可看到 `Uvicorn running on http://0.0.0.0:8900`。

---

## 6. 验证部署

### 6.1 健康检查

```bash
curl http://localhost:8900/api/stats
# 预期返回：{"total":0,"pending":0,"processing":0,"completed":0,"failed":0,"avg_duration_ms":0}
```

### 6.2 访问界面

浏览器打开 `http://<目标机器IP>:8900`，应看到 MinerU Batch 概览页。

### 6.3 Docker 健康检查

镜像内置了 `HEALTHCHECK`，约 30 秒后自动检测：

```bash
docker inspect --format='{{.State.Health.Status}}' $(docker compose ps -q app)
# 预期：healthy
```

---

## 7. 配置 MinerU 服务

系统本身不内置 MinerU 解析能力，需配置外部 MinerU API 地址。

1. 浏览器打开 `http://<IP>:8900` → 点击左侧 **系统设置**
2. 填写 MinerU 服务地址（如 `http://mineru-server:8888`）
3. 点击 **测试连接** 确认可达
4. 保存配置

> MinerU API 地址必须是目标机器**可访问**的内网地址。

---

## 8. 数据持久化

所有运行数据存储在 Docker Volume `data` 中：

| 路径 | 内容 |
|------|------|
| `/data/uploads/` | 上传的原始文件 |
| `/data/outputs/` | 解析输出结果 |
| `/data/converted/` | Office 转 PDF 中间文件 |
| `/data/mineru_batch.db` | SQLite 数据库 |

### 8.1 查看数据卷位置

```bash
docker volume inspect mineru-batch_data
```

### 8.2 备份数据

```bash
# 备份数据库
docker compose exec app cp /data/mineru_batch.db /data/mineru_batch.db.bak

# 或直接从宿主机拷贝
sudo cp $(docker volume inspect mineru-batch_data --format '{{.Mountpoint}}')/mineru_batch.db ./backup/
```

### 8.3 清理磁盘

在 **系统设置** 页面点击 **存储管理**，可清理已完成任务的源文件和输出文件。

---

## 9. 常用运维命令

```bash
# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看实时日志
docker compose logs -f

# 更新镜像（重新部署时）
docker compose down
gunzip -c mineru-batch-v0.1.0.tar.gz | docker load
docker compose up -d

# 进入容器调试
docker compose exec app bash

# 查看磁盘占用
docker system df
```

---

## 10. 端口与防火墙

服务监听 `8900` 端口。如需限制访问：

```bash
# 仅允许内网 10.0.0.0/8 访问
sudo iptables -A INPUT -p tcp --dport 8900 -s 10.0.0.0/8 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8900 -j DROP
```

如需更换端口，修改 `docker-compose.yml` 的 `ports` 配置：

```yaml
ports:
  - "9000:8900"  # 宿主机 9000 → 容器 8900
```

---

## 11. 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 容器启动后立即退出 | 镜像未正确加载 | 重新执行 `docker load` |
| 页面无法访问 | 端口未开放或容器未运行 | 检查 `docker compose ps`，确认端口映射 |
| 任务一直 pending | MinerU API 未配置或不可达 | 设置页配置 API 地址并测试连接 |
| Office 文件转 PDF 失败 | LibreOffice 内存不足 | 增加容器内存限制 |
| 上传大文件报 413 | Nginx 反代限制 | 调整 `client_max_body_size` |
| SSE 显示离线 | 网络代理中断 EventSource | 检查反向代理配置，确保不缓冲 SSE |

### 查看详细日志

```bash
# 应用日志
docker compose logs --tail=100 app

# 容器内数据库状态
docker compose exec app python -c "
from sqlalchemy import create_engine, text
engine = create_engine('sqlite:////data/mineru_batch.db')
with engine.connect() as conn:
    print(conn.execute(text('SELECT status, count(*) FROM file_tasks GROUP BY status')).fetchall())
"
```

---

## 12. 离线卸载

```bash
docker compose down -v    # 停止并删除容器+数据卷
docker rmi mineru-batch:v0.1.0  # 删除镜像
rm -rf /opt/mineru-batch   # 删除部署目录
```

> `-v` 会删除所有数据，如需保留数据请去掉该参数。
