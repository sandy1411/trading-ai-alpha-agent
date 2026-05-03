# Database Setup

## Do You Need Docker Desktop?

Not strictly, but it is the easiest Windows setup for this project.

You have three choices:

1. Docker Desktop with WSL 2: recommended for local development.
2. Native PostgreSQL installed on Windows: works, but you manage the service yourself.
3. Managed PostgreSQL: good later, not needed for local development.

For this machine, Docker and WSL are not currently installed. The recommended path is Docker Desktop with WSL 2.

Official references:

- Microsoft WSL install: https://learn.microsoft.com/en-us/windows/wsl/install
- Docker Desktop Windows install: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker Desktop WSL 2 backend: https://docs.docker.com/docker-for-windows/wsl/

## Do You Need PostgreSQL?

Yes, before any serious shadow-live trading workflow.

The app can run `/health` and tests without PostgreSQL today, but real shadow-live validation needs durable storage for:

- audit logs
- system state
- kill switch state
- broker/provider health
- risk decisions
- order lifecycle
- reconciliation state
- compliance state

## Do You Need Redis?

Not right now.

Redis is optional in this phase. It will be useful later for queues, caches, locks, schedulers, and background workers, but Zerodha shadow-live setup does not require it.

## Recommended Local Setup

Install WSL from an Administrator PowerShell:

```powershell
wsl --install
```

Reboot if Windows asks you to.

Install Docker Desktop:

```powershell
winget install Docker.DockerDesktop
```

Or run the repo helper from an Administrator PowerShell:

```powershell
.\scripts\install_windows_prereqs.cmd
```

Open Docker Desktop once and make sure it starts. Then reopen PowerShell.

Start only PostgreSQL:

```powershell
cd "C:\Users\Sandeep.Pathak\Documents\New project\dalalwall-ai-alpha-agent"
.\scripts\docker_up.cmd
```

Check database health:

```powershell
.\scripts\db_status.cmd
```

Open a database shell without installing local `psql`:

```powershell
.\scripts\db_shell.cmd
```

Start Redis too, only when needed:

```powershell
.\scripts\docker_up.cmd -WithRedis
```

## Connection String

The local Docker PostgreSQL connection is:

```env
DATABASE_URL=postgresql+psycopg://dalalwall:dalalwall@localhost:5432/dalalwall_ai_alpha
```

This is already in `.env.example`.

## Stop Services

```powershell
docker compose stop
```

To remove containers but keep named volumes:

```powershell
docker compose down
```

To remove database data too, use this only when you are sure:

```powershell
docker compose down -v
```
