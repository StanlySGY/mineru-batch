#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="mineru-batch"
VERSION=$(cat VERSION | tr -d ' \t\n\r')
OUTPUT="${IMAGE_NAME}-${VERSION}.tar.gz"

echo "=== 构建镜像: ${IMAGE_NAME}:${VERSION} ==="
docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" .

echo ""
echo "=== 导出镜像: ${OUTPUT} ==="
docker save "${IMAGE_NAME}:${VERSION}" | gzip > "${OUTPUT}"

echo ""
echo "=== 完成 ==="
echo "镜像: ${IMAGE_NAME}:${VERSION}（同时打了 latest 标签）"
echo "文件: $(pwd)/${OUTPUT}"
echo ""
echo "=== 部署到目标机器 ==="
echo ""
echo "1. 将 ${OUTPUT} 传到目标机器"
echo ""
echo "2. 在目标机器上加载镜像:"
echo "   gunzip -c ${OUTPUT} | docker load"
echo ""
echo "3. 启动（docker-compose，自动使用 latest 标签）:"
echo "   docker compose up -d"
echo ""
echo "   或指定特定版本:"
echo "   TAG=${VERSION} docker compose up -d"
