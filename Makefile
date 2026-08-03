# ArbiCore X — Operator Makefile
# Convenience wrapper over scripts/ and deployment/compose/.
# All targets are idempotent and self-documenting via `make help`.

SHELL := /bin/bash
REPO_ROOT := $(shell pwd)
COMPOSE_DIR := $(REPO_ROOT)/deployment/compose

# Default docker compose invocation (v2 preferred, v1 fallback)
DC := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; \
              elif command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; \
              else echo "false"; fi)

.PHONY: help install upgrade upgrade-full rollback up down restart logs status \
        healthcheck backup restore test-backend build env-check version clean verify

help:
	@echo "ArbiCore X — operator commands"
	@echo ""
	@echo "  Lifecycle"
	@echo "    make install         Greenfield install on a clean VPS (guarded, 9-phase)"
	@echo "    make upgrade         Safe upgrade (detect/preflight/backup/index-audit, stops for review)"
	@echo "    make upgrade-full    Full upgrade chain including build/cutover/canary/validate/snapshot"
	@echo "    make rollback        Rollback the last upgrade"
	@echo ""
	@echo "  Runtime"
	@echo "    make up              Start all services (no cert issuance)"
	@echo "    make down            Stop all services (data preserved)"
	@echo "    make restart         Restart all services"
	@echo "    make logs SERVICE=x  Tail logs for a service (default: all)"
	@echo "    make status          docker compose ps"
	@echo "    make healthcheck     Read-only aggregate health probe"
	@echo ""
	@echo "  Release verification (v1.0.2+)"
	@echo "    make verify DOMAIN=<url> PROFILE=<shared|greenfield>"
	@echo "                         Run the 8-category deployment verification harness."
	@echo "                         Optional: ADMIN_USER=admin ADMIN_PASS='...' for cats. 7/8."
	@echo ""
	@echo "  Data safety"
	@echo "    make backup          Snapshot Mongo (archive.gz in ./backups/)"
	@echo "    make restore ARCHIVE=./backups/x.gz   Restore from a backup archive"
	@echo ""
	@echo "  Development"
	@echo "    make build           Build all Docker images"
	@echo "    make test-backend    Run backend pytest suite inside the container"
	@echo "    make env-check       Validate that .env has all required keys"
	@echo "    make version         Print current version"
	@echo ""
	@echo "  Meta"
	@echo "    make help            This message"

# --- Lifecycle ---
install:
	@bash scripts/install.sh

upgrade:
	@bash scripts/upgrade.sh safe

upgrade-full:
	@bash scripts/upgrade.sh full

rollback:
	@bash scripts/upgrade.sh rollback

# --- Runtime ---
up:
	@cd $(COMPOSE_DIR) && $(DC) up -d

down:
	@cd $(COMPOSE_DIR) && $(DC) down

restart:
	@cd $(COMPOSE_DIR) && $(DC) restart

logs:
	@cd $(COMPOSE_DIR) && $(DC) logs -f --tail=200 $(SERVICE)

status:
	@cd $(COMPOSE_DIR) && $(DC) ps

healthcheck:
	@bash scripts/healthcheck.sh

# --- Release verification (v1.0.2+) -----------------------------------------
# 8-category post-deployment verification harness. Runs the standard release
# checklist. See scripts/README.md and docs/releases/v1.0.2.md.
#
# Usage:
#   make verify DOMAIN=https://arbicore.example.com PROFILE=shared
#   make verify DOMAIN=https://arbicore.example.com PROFILE=shared \
#               ADMIN_USER=admin ADMIN_PASS='s3cr3t'
#
# Optional flags:
#   SKIP_BROWSER=1     # skip Playwright checks (categories 5 + 8)
#   JSON=/tmp/out.json # also write machine-readable results
verify:
	@if [ -z "$(DOMAIN)" ]; then echo "Usage: make verify DOMAIN=<url> PROFILE=<shared|greenfield> [ADMIN_USER=... ADMIN_PASS=...]"; exit 2; fi
	@if [ -z "$(PROFILE)" ]; then echo "Usage: make verify DOMAIN=<url> PROFILE=<shared|greenfield>"; exit 2; fi
	@bash scripts/verify-deployment.sh \
	    --domain "$(DOMAIN)" \
	    --profile "$(PROFILE)" \
	    $(if $(ADMIN_USER),--admin-user "$(ADMIN_USER)") \
	    $(if $(ADMIN_PASS),--admin-pass "$(ADMIN_PASS)") \
	    $(if $(SKIP_BROWSER),--skip-browser) \
	    $(if $(JSON),--json "$(JSON)")

# --- Data safety ---
backup:
	@bash scripts/backup.sh

restore:
	@if [ -z "$(ARCHIVE)" ]; then echo "Usage: make restore ARCHIVE=./backups/x.gz"; exit 2; fi
	@bash scripts/restore.sh "$(ARCHIVE)"

# --- Development ---
build:
	@cd $(COMPOSE_DIR) && $(DC) build

build-backend:
	@cd $(COMPOSE_DIR) && $(DC) build backend

build-frontend:
	@cd $(COMPOSE_DIR) && $(DC) build frontend

build-oc:
	@cd $(COMPOSE_DIR) && $(DC) build opportunity_center

test-backend:
	@cd $(COMPOSE_DIR) && $(DC) exec -T backend python -m pytest tests/ --tb=short -q

env-check:
	@if [ ! -f .env ]; then echo ".env not found. Copy .env.example first."; exit 2; fi
	@set -a; source .env; set +a; \
	 for var in DOMAIN LETSENCRYPT_EMAIL JWT_SECRET VAULT_KEY MONGO_URL DB_NAME; do \
	   if [ -z "$${!var:-}" ]; then echo "MISSING: $$var"; exit 2; fi; \
	   echo "  OK  $$var"; \
	 done

version:
	@cat VERSION
