# `docs/` — Documentation index

Operational, architectural, and governance documentation for ArbiCore X. Every doc here describes the *current* system — historical material is out of scope for this directory and lives only in `docs/MIGRATION_SUMMARY.md` for provenance.

## Where to start

| I want to… | Read |
|---|---|
| Understand what the system is and how it fits together | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Install ArbiCore X on a fresh Ubuntu VPS | [`INSTALL.md`](INSTALL.md) |
| Operate a running install (start/stop/logs/status) | [`OPERATIONS.md`](OPERATIONS.md) |
| Upgrade the backend safely | [`UPGRADE.md`](UPGRADE.md) |
| Roll back a failed upgrade | [`ROLLBACK.md`](ROLLBACK.md) |
| Back up or restore Mongo data | [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md) |
| Issue / renew / troubleshoot Let's Encrypt certs | [`SSL.md`](SSL.md) |
| Understand and harden the security posture | [`SECURITY.md`](SECURITY.md) |
| Diagnose a problem | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |
| Deploy alongside an existing peer stack on a multi-tenant VPS | [`SHARED_INFRASTRUCTURE.md`](SHARED_INFRASTRUCTURE.md) |
| Understand *why* the repository is structured the way it is | [`REPOSITORY_PHILOSOPHY.md`](REPOSITORY_PHILOSOPHY.md) |
| See the repository's long-term direction and governance rules | [`ROADMAP.md`](ROADMAP.md) |
| Trace where every file in the canonical repo came from | [`MIGRATION_SUMMARY.md`](MIGRATION_SUMMARY.md) |
| See what was intentionally left out of the canonical repo | [`EXCLUSIONS.md`](EXCLUSIONS.md) |
| Confirm the repository has been certified as the canonical baseline | [`CANONICAL_CERTIFICATION.md`](CANONICAL_CERTIFICATION.md) |

## Rules

- Every operational doc reflects the current implementation. If the implementation changes, the doc must change in the same commit.
- No doc contains a link to a legacy repository *as if it were canonical*. Legacy repos may be referenced only from `MIGRATION_SUMMARY.md` as historical evidence.
- No doc contains hard-coded IPs, FQDNs, or non-example credentials.
