#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== 启动 MinerU Batch Processor ==="

# Kill stale processes
pkill -f "uvicorn main:app.*8900" 2>/dev/null || true
pkill -f "vite.*3001" 2>/dev/null || true
sleep 1

# Backend
echo "[1/2] 启动后端 (FastAPI :8900) ..."
cd "$ROOT/backend"
pip install -q fastapi uvicorn sqlalchemy httpx python-multipart aiofiles slowapi markdown --break-system-packages 2>/dev/null
setsid python3 -m uvicorn main:app --host 0.0.0.0 --port 8900 --log-level info > /tmp/mineru_backend.log 2>&1 &
BACK_PID=$!

# Frontend
echo "[2/2] 启动前端 (Vite :3001) ..."
cd "$ROOT/frontend"
npm install --silent 2>/dev/null
setsid npx vite --host 0.0.0.0 --port 3001 > /tmp/mineru_frontend.log 2>&1 &
FRONT_PID=$!

# Wait for backend to be ready
for i in $(seq 1 15); do
  if curl -s --max-time 1 http://localhost:8900/api/stats > /dev/null 2>&1; then
    echo "后端就绪"
    break
  fi
  sleep 1
done

echo ""
echo "=== 服务已启动 ==="
echo "前端地址: http://localhost:3001"
echo "后端地址: http://localhost:8900/docs"
echo "后端日志: tail -f /tmp/mineru_backend.log"
echo "前端日志: tail -f /tmp/mineru_frontend.log"
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACK_PID $FRONT_PID 2>/dev/null; pkill -f 'uvicorn main:app.*8900' 2>/dev/null; pkill -f 'vite.*3001' 2>/dev/null; exit" INT TERM
wait
