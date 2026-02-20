# Use bash so we can write slightly nicer shell logic
SHELL := /bin/bash

# Where we store PID files (so "make stop" can kill the servers)
PID_DIR := .pids
API_PID := $(PID_DIR)/api.pid
WEB_PID := $(PID_DIR)/web.pid

# Explicit paths (avoid "source" and avoid relying on your interactive venv)
API_UVICORN := ./apps/api/.venv/bin/uvicorn

# Ports used in dev
API_PORT := 8000
WEB_PORT := 3000

.PHONY: dev db api web stop down status logs

# "make dev" starts everything
dev: db api web
	@echo "✅ Dev stack running:"
	@echo "   - DB: docker compose (service: db)"
	@echo "   - API: http://127.0.0.1:$(API_PORT)"
	@echo "   - Web: http://127.0.0.1:$(WEB_PORT)"

# Start only the database container
db:
	docker compose up -d db

# Start FastAPI backend in the background and save PID
api:
	mkdir -p $(PID_DIR)
	@# Kill anything already listening on the API port (prevents "ghost" reload processes)
	@P=$$(lsof -ti tcp:$(API_PORT)); if [ -n "$$P" ]; then kill -9 $$P 2>/dev/null || true; fi
	@# Key fix: --app-dir apps/api so "app.main:app" imports correctly from repo root
	nohup $(API_UVICORN) --app-dir apps/api app.main:app --reload --port $(API_PORT) \
		> api.log 2>&1 & echo $$! > $(API_PID)
	@echo "🚀 API started (pid $$(cat $(API_PID)))"

# Start Next.js frontend in the background and save PID
web:
	mkdir -p $(PID_DIR)
	@# Kill anything already listening on the Web port (prevents orphan node processes)
	@P=$$(lsof -ti tcp:$(WEB_PORT)); if [ -n "$$P" ]; then kill -9 $$P 2>/dev/null || true; fi
	@# Key fix: use npm --prefix so we don't rely on "cd ... && ../../"
	nohup npm --prefix apps/web run dev > web.log 2>&1 & echo $$! > $(WEB_PID)
	@echo "🌐 Web started (pid $$(cat $(WEB_PID)))"

# Stop web + api (even if PID files are stale) using BOTH pidfiles and port-kill
stop:
	@echo "🛑 Stopping dev servers..."
	@# Stop by PID files if they exist
	@if [ -f "$(API_PID)" ]; then kill $$(cat "$(API_PID)") 2>/dev/null || true; rm -f "$(API_PID)"; fi
	@if [ -f "$(WEB_PID)" ]; then kill $$(cat "$(WEB_PID)") 2>/dev/null || true; rm -f "$(WEB_PID)"; fi
	@# Stop by ports (covers uvicorn --reload child processes and Next.js child processes)
	@P=$$(lsof -ti tcp:$(API_PORT)); if [ -n "$$P" ]; then kill -9 $$P 2>/dev/null || true; fi
	@P=$$(lsof -ti tcp:$(WEB_PORT)); if [ -n "$$P" ]; then kill -9 $$P 2>/dev/null || true; fi
	@echo "✅ API/Web stopped"

# Bring down docker (and also stop local servers)
down: stop
	docker compose down

# Show what's listening on ports (useful debug)
status:
	@echo "---- LISTENERS ----"
	@lsof -nP -iTCP:$(API_PORT) -sTCP:LISTEN || true
	@lsof -nP -iTCP:$(WEB_PORT) -sTCP:LISTEN || true
	@echo "---- PID FILES ----"
	@ls -l $(PID_DIR) 2>/dev/null || true

# Tail logs
logs:
	@echo "---- api.log (last 60) ----"
	@tail -n 60 api.log 2>/dev/null || true
	@echo "---- web.log (last 60) ----"
	@tail -n 60 web.log 2>/dev/null || true
