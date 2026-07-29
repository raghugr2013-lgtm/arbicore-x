# Convenience wrappers for the realignment steps. Mirrors EXECUTION_ORDER.md exactly.
# Each target invokes the matching script — nothing happens implicitly.
SHELL := /usr/bin/env bash
ROOT  := $(shell pwd)

.PHONY: detect preflight backup index-audit cleanup build cutover canary validate snapshot rollback all

detect:
	@$(ROOT)/steps/00_detect_env.sh

preflight:
	@$(ROOT)/steps/01_preflight.sh

backup:
	@$(ROOT)/steps/02_backup.sh

index-audit:
	@$(ROOT)/steps/03_index_audit.sh

# Opt-in deletion; requires --confirm on the underlying script.
cleanup:
	@$(ROOT)/steps/04_precutover_cleanup.sh --confirm

build:
	@$(ROOT)/steps/05_build.sh

cutover:
	@$(ROOT)/steps/06_cutover.sh

canary:
	@$(ROOT)/steps/09_canary_probe.sh

validate:
	@$(ROOT)/steps/10_validate.sh

snapshot:
	@$(ROOT)/steps/11_snapshot.sh

rollback:
	@$(ROOT)/steps/99_rollback.sh

# "all" stops at backup on purpose. The risky steps (build/cutover) stay manual.
all: detect preflight backup index-audit
	@echo
	@echo "Stopped before build/cutover on purpose. Continue manually:"
	@echo "  make build      # safe: builds image, old keeps serving"
	@echo "  make cutover    # the downtime window"
	@echo "  make canary     # 60s read-only canary; auto-rollback on threshold"
	@echo "  make validate   # acceptance"
	@echo "  make snapshot   # observability"
	@echo "  make rollback   # if needed"
