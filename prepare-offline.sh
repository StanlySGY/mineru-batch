#!/bin/bash

# 为离线环境准备 mineru-batch 镜像和文件

set -e

VERSION=$(cat VERSION)
ARCHIVE_NAME="mineru-batch-offline-${VERSION}"
TEMP_DIR=$(mktemp -d)

echo "📦 准备离线部署包..."
echo "版本: $VERSION"
echo "临时目录: $TEMP_DIR"

# 1. 构建镜像
echo "🔨 构建 Docker 镜像..."
docker build -t mineru-batch:${VERSION} .

# 2. 导出镜像
echo "💾 导出镜像为 tar 文件..."
docker save mineru-batch:${VERSION} -o "${TEMP_DIR}/mineru-batch-${VERSION}.tar"

# 3. 压缩镜像
echo "📦 压缩镜像..."
gzip "${TEMP_DIR}/mineru-batch-${VERSION}.tar"

# 4. 复制配置文件
echo "📋 复制配置文件..."
mkdir -p "${TEMP_DIR}/config"
cp docker-compose.yml "${TEMP_DIR}/config/"
cp VERSION "${TEMP_DIR}/config/"
cp Dockerfile "${TEMP_DIR}/config/"

# 5. 创建部署脚本
cat > "${TEMP_DIR}/config/deploy.sh" << 'EOF'
#!/bin/bash
# 离线环境部署脚本

set -e

VERSION=$(cat VERSION)
IMAGE_FILE="mineru-batch-${VERSION}.tar.gz"

echo "📥 导入 Docker 镜像..."
docker load -i "${IMAGE_FILE}"

echo "🚀 启动容器..."
docker-compose up -d

echo "✅ 部署完成！"
echo "访问地址: http://localhost:8900"
echo ""
echo "查看日志: docker-compose logs -f"
echo "停止服务: docker-compose down"
EOF

chmod +x "${TEMP_DIR}/config/deploy.sh"

# 6. 创建说明文档
cat > "${TEMP_DIR}/README.md" << 'EOF'
# MinerU Batch 离线部署指南

## 文件说明

- `mineru-batch-v*.tar.gz` - Docker 镜像文件（已包含所有依赖）
- `docker-compose.yml` - Docker Compose 配置
- `deploy.sh` - 自动部署脚本
- `VERSION` - 版本号

## 部署步骤

### 方式 1：使用自动脚本（推荐）

```bash
cd config
bash deploy.sh
```

### 方式 2：手动部署

```bash
# 1. 导入镜像
docker load -i mineru-batch-v*.tar.gz

# 2. 启动服务
cd config
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

## 访问应用

- **Web UI**: http://localhost:8900
- **API**: http://localhost:8900/api

## 数据持久化

所有数据存储在 Docker volume `data` 中：
- `/data/uploads` - 上传的文件
- `/data/outputs` - 处理结果
- `/data/converted` - 转换后的 PDF
- `/data/mineru_batch.db` - SQLite 数据库

## 停止服务

```bash
cd config
docker-compose down
```

## 升级镜像

如果有新版本，只需替换 `mineru-batch-v*.tar.gz` 文件，重新运行 `deploy.sh` 即可。

## 故障排查

查看容器日志：
```bash
docker-compose logs app
```

进入容器调试：
```bash
docker-compose exec app bash
```

EOF

# 7. 打包所有文件
echo "📦 打包所有文件..."
cd "${TEMP_DIR}"
tar -czf "${ARCHIVE_NAME}.tar.gz" .

# 8. 移动到当前目录
mv "${ARCHIVE_NAME}.tar.gz" "${OLDPWD}/"

# 9. 清理临时文件
rm -rf "${TEMP_DIR}"

echo ""
echo "✅ 完成！"
echo "📦 离线部署包: ${ARCHIVE_NAME}.tar.gz"
echo ""
echo "使用方法："
echo "  1. 将 ${ARCHIVE_NAME}.tar.gz 复制到离线环境"
echo "  2. 解压: tar -xzf ${ARCHIVE_NAME}.tar.gz"
echo "  3. 部署: cd config && bash deploy.sh"
