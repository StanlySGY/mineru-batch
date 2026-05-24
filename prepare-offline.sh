#!/bin/bash
set -euo pipefail

VERSION=$(tr -d ' \t\n\r' < VERSION)
ARCHIVE_NAME="mineru-batch-offline-${VERSION}"
IMAGE_FILE="mineru-batch-${VERSION}.tar.gz"
TEMP_DIR=$(mktemp -d)
ROOT_DIR=$(pwd)

cleanup() {
  rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

echo "准备离线部署包..."
echo "版本: ${VERSION}"

echo "构建 Docker 镜像..."
docker build -t "mineru-batch:${VERSION}" .

echo "导出镜像..."
docker save "mineru-batch:${VERSION}" | gzip > "${TEMP_DIR}/${IMAGE_FILE}"

echo "复制部署文件..."
cp docker-compose.yml "${TEMP_DIR}/docker-compose.yml"
cp VERSION "${TEMP_DIR}/VERSION"
cat > "${TEMP_DIR}/.env" << EOF
TAG=${VERSION}
APP_PORT=8900
TZ=Asia/Shanghai
ADMIN_API_KEY=
ALLOW_PRIVATE_ENDPOINTS=true
EOF

cat > "${TEMP_DIR}/deploy.sh" << 'EOF'
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION=$(tr -d ' \t\n\r' < "${SCRIPT_DIR}/VERSION")
IMAGE_FILE="${SCRIPT_DIR}/mineru-batch-${VERSION}.tar.gz"

if [ ! -f "${IMAGE_FILE}" ]; then
  echo "找不到镜像文件: ${IMAGE_FILE}"
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "未找到 docker compose 或 docker-compose"
  exit 1
fi

echo "导入 Docker 镜像..."
gunzip -c "${IMAGE_FILE}" | docker load

echo "启动容器..."
"${COMPOSE[@]}" --env-file "${SCRIPT_DIR}/.env" -f "${SCRIPT_DIR}/docker-compose.yml" up -d

echo "部署完成: http://localhost:8900"
echo "查看日志: ${COMPOSE[*]} --env-file ${SCRIPT_DIR}/.env -f ${SCRIPT_DIR}/docker-compose.yml logs -f"
EOF
chmod +x "${TEMP_DIR}/deploy.sh"

cat > "${TEMP_DIR}/README.md" << 'EOF'
# MinerU Batch 离线部署指南

## 文件说明

- `mineru-batch-v*.tar.gz`：Docker 镜像文件
- `docker-compose.yml`：部署配置
- `.env`：运行配置，升级时由 `TAG` 控制镜像版本
- `deploy.sh`：离线部署/升级脚本
- `VERSION`：当前版本号

## 部署

```bash
bash deploy.sh
```

默认访问地址：http://localhost:8900

## 生产配置建议

部署前编辑 `.env`：

```bash
ADMIN_API_KEY=请填写强随机密钥
ALLOW_PRIVATE_ENDPOINTS=true
APP_PORT=8900
```

设置 `ADMIN_API_KEY` 后，前端“系统设置”页需要填入相同的管理员 Key 才能执行保存配置、删除、重试、清理等管理操作。

## 升级

1. 备份 Docker volume `data`。
2. 解压新版离线包。
3. 确认 `.env` 中 `TAG` 为新版 VERSION。
4. 运行 `bash deploy.sh`。

## 常用命令

```bash
docker compose --env-file .env -f docker-compose.yml logs -f
docker compose --env-file .env -f docker-compose.yml down
docker compose --env-file .env -f docker-compose.yml ps
```

所有运行数据位于 Docker volume `data` 中。
EOF

cd "${TEMP_DIR}"
tar -czf "${ARCHIVE_NAME}.tar.gz" .
mv "${ARCHIVE_NAME}.tar.gz" "${ROOT_DIR}/"

echo "完成: ${ROOT_DIR}/${ARCHIVE_NAME}.tar.gz"
