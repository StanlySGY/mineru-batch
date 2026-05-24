#!/bin/bash
set -euo pipefail

PACKAGE=${1:-}

if [ -z "${PACKAGE}" ]; then
  echo "用法: bash update-offline.sh mineru-batch-offline-vX.Y.Z.tar.gz"
  exit 1
fi

if [ ! -f "${PACKAGE}" ]; then
  echo "找不到离线包: ${PACKAGE}"
  exit 1
fi

WORK_DIR=$(mktemp -d)
cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

echo "解压离线包..."
tar -xzf "${PACKAGE}" -C "${WORK_DIR}"

echo "执行镜像级升级..."
cd "${WORK_DIR}"
bash deploy.sh

echo "升级完成。建议确认服务健康后再清理旧镜像。"
