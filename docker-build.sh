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
echo "镜像: ${IMAGE_NAME}:${VERSION}"
echo "文件: $(pwd)/${OUTPUT}"
echo ""
echo "导入命令（在目标机器上执行）:"
echo "  gunzip -c ${OUTPUT} | docker load"
echo "  docker run -d -p 8900:8900 -v mineru_data:/data --restart unless-stopped ${IMAGE_NAME}:${VERSION}"
