# Windows Setup

This machine currently has Git available, but Docker, Docker Compose, Python on PATH, `psql`, and GitHub CLI were not detected.

## 1. Check Current Tools

```powershell
cd "C:\Users\Sandeep.Pathak\Documents\New project\dalalwall-ai-alpha-agent"
.\scripts\setup_check.ps1
```

The Codex bundled Python can run tests and FastAPI, but installing Python 3.11+ normally is recommended for day-to-day use.

## 2. Install Docker Desktop

Install Docker Desktop for Windows with the WSL 2 backend from Docker's official docs:

https://docs.docker.com/desktop/setup/install/windows-install/

After installation, reopen PowerShell and check:

```powershell
docker --version
docker compose version
```

Then start PostgreSQL:

```powershell
.\scripts\docker_up.cmd
```

Redis is optional for the current phase. To start it too:

```powershell
.\scripts\docker_up.cmd -WithRedis
```

See `docs/database_setup.md` for the database decision guide.

## 3. Install Python

Install Python 3.11+ from:

https://www.python.org/downloads/windows/

Make sure "Add python.exe to PATH" is selected.

Then:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .[dev]
```

## 4. Configure Environment

```powershell
Copy-Item .env.example .env
```

Keep these values until shadow-live validation is complete:

```env
TRADING_MODE=SHADOW_LIVE
LIVE_TRADING_ENABLED=false
LIVE_ORDERS_ENABLED=false
KILL_SWITCH=true
```

## 5. Run The API

```powershell
.\scripts\run_api.ps1
```

Open:

http://127.0.0.1:8000/health

## 6. Run Tests

```powershell
python -m pytest
```

If system Python is still not available, use the bundled runtime:

```powershell
& "C:\Users\Sandeep.Pathak\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest
```
