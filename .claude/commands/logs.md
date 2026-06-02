# /logs

Tail live logs for all running Docker containers.

## Steps
1. Check containers are running: `docker compose ps`
2. If containers are down, report which ones and suggest `docker compose up -d`
3. If running, tail all logs: `docker compose logs -f`
