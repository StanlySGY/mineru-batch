#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="mineru-batch"
VERSION=$(cat VERSION | tr -d ' \t\n\r')
OUTPUT="${IMAGE_NAME}-${VERSION}.tar.gz"

echo "=== 构建镜像: ${IMAGE_NAME}:${VERSION} ==="
docker build -t "${IMAGE_NAME}:${VERSION}" .

echo ""
echo "=== 导出镜像: ${OUTPUT} ==="
docker save "${IMAGE_NAME}:${VERSION}" | gzip > "${OUTPUT}"

# 生成 .env 供 docker compose 自动读取（仅更新 TAG，保留其他配置）
if [ -f .env ]; then
  if grep -q '^TAG=' .env; then
    sed -i "s/^TAG=.*/TAG=${VERSION}/" .env
  else
    echo "TAG=${VERSION}" >> .env
  fi
else
  echo "TAG=${VERSION}" > .env
fi

echo ""
echo "=== 完成 ==="
echo "镜像: ${IMAGE_NAME}:${VERSION}"
echo "文件: $(pwd)/${OUTPUT}"
echo ""
echo "=== 部署到目标机器 ==="
echo ""
echo "1. 将 ${OUTPUT} 传到目标机器"
echo ""
echo "2. 在目标机器上加载镜像:"
echo "   gunzip -c ${OUTPUT} | docker load"
echo ""
echo "3. 启动（.env 已写入 TAG=${VERSION}）:"
echo "   docker compose up -d"
