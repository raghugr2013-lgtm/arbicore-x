# /app/vps_cert/ — certification output

`certification_report.md` + `certification_evidence.json` here are the **in-pod
DRY-RUN** produced without operator RPCs — every check is `NOT_CONFIGURED` /
`BLOCKED` (status_counts show **zero PASS**). This is the correct fail-closed
proof that the harness never fabricates evidence.

The **real** certification report is produced ON THE VPS by running
`deployment/cert/VPS_CERTIFICATION_RUNBOOK.md` (the one-shot `certify` service in
`deployment/compose/docker-compose.certification.yml`), which regenerates these
two files into `./vps_cert_out/` on the VPS host using the operator's read-only
RPCs. No secret (RPC URL / API key) is ever written into either file — only
redacted `host:port`, booleans, public on-chain addresses, and statuses.
