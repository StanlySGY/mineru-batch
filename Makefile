.PHONY: dev dev-frontend dev-backend build prod test clean

# 开发模式（前后端分离，支持 HMR）
dev:
	@echo "=== 开发模式 ==="
	@make -j2 dev-frontend dev-backend

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && DEV_MODE=1 uvicorn main:app --host 0.0.0.0 --port 8900 --reload

# 构建
build:
	cd frontend && npm install && npm run build

# 生产模式（单进程）
prod: build
	cd backend && uvicorn main:app --host 0.0.0.0 --port 8900

# 测试
test:
	cd backend && python -m pytest tests/ -v

# 清理
clean:
	rm -rf frontend/dist
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
