---
description: Validate Docker Compose configuration and ARM64 compatibility. Triggered when editing docker-compose.yml, adding new services, or changing base images.
---

# Docker Validate Skill

## When to Use
- After any edit to docker-compose.yml
- When adding a new container or service
- When changing a base image
- Before running `docker compose up` for the first time

## Steps
1. Run `docker compose config --quiet` to validate syntax
2. Check every service has `platform: linux/arm64`
3. Verify base images are ARM64-compatible (see `.claude/rules/infrastructure.md` for valid images)
4. Confirm all volumes declared at the bottom
5. Confirm `insurance-net` bridge network is declared
6. Report any issues found
