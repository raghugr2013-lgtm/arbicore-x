# G1.6 frozen-data before/after

- Generated: `2026-10-09T05:25:15Z`
- Source: `MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl` sha256 `f525083f2ef218ce4532993c1dcc41e8807d0db68824408d9d4675d4ad871714`
- Base rows: **6287**
- Original classification counts: `{'A': 1418, 'D': 560, 'B': 4252, 'C': 57}`
- Classification unchanged after guard: **True**
- Flag counts: `{'NO_FLAG': 6065, 'POTENTIAL_CROSS_TX_MIRROR': 118, 'REPEATED_POOL_ROUTE': 98, 'BOTH_FLAGS': 6}`
- Unique mirror pairs: **68** (raw link rows 88)
- Flagged rows: **222**

## Sample flagged (up to 25)

| tx | flag | orig class | orig NET | bundle NET | peers |
|---|---|---|---|---|---|
| `0xafb93ba12839670b…` | BOTH_FLAGS | B | 19.497664 | 19.874782 | 0x5a5b5fa2… |
| `0xbf05083ded82ff5f…` | BOTH_FLAGS | B | 6.518886 | 7.991047 | 0xae6c226c… |
| `0xae6c226c41242c3a…` | BOTH_FLAGS | B | 1.472161 | 7.991047 | 0xbf05083d… |
| `0xbe4333553f191374…` | BOTH_FLAGS | B | 0.208399 | 0.233541 | 0xb7f3a0be… |
| `0x48ca1775b844a656…` | BOTH_FLAGS | B | 0.090874 | 18.112832 | 0x84472f5f… |
| `0x613c32369e21ebc1…` | BOTH_FLAGS | D | None | 0.724357 | 0x239678a4… |
| `0xff34b616ce0db6f5…` | REPEATED_POOL_ROUTE | C | 4797.12786 | None |  |
| `0x77bb2502032303dc…` | REPEATED_POOL_ROUTE | B | 284.222727 | None |  |
| `0xab8150fa154f3c49…` | REPEATED_POOL_ROUTE | B | 261.754048 | None |  |
| `0x0e87fecc26f646ce…` | REPEATED_POOL_ROUTE | B | 244.432083 | None |  |
| `0xc3d35e72da0d6bd2…` | REPEATED_POOL_ROUTE | B | 144.67577 | None |  |
| `0x9b80fd7dea802ebf…` | POTENTIAL_CROSS_TX_MIRROR | A | 76.403353 | 154.408534 | 0x6800a3da… |
| `0x6800a3da2c487294…` | POTENTIAL_CROSS_TX_MIRROR | A | 74.850419 | 154.408534 | 0x9b80fd7d…,0xa50b9ad2… |
| `0x2511dc9797d2408e…` | REPEATED_POOL_ROUTE | C | 72.713488 | None |  |
| `0xa4e73bd9cf7e7580…` | POTENTIAL_CROSS_TX_MIRROR | A | 26.297948 | 30.200534 | 0xe4400f23… |
| `0xf34b5fa614b351f0…` | REPEATED_POOL_ROUTE | C | 25.627352 | None |  |
| `0xf07e3ad7eea2c515…` | REPEATED_POOL_ROUTE | B | 22.540317 | None |  |
| `0xdeaa523094bf9c83…` | REPEATED_POOL_ROUTE | B | 20.754224 | None |  |
| `0xf655cf4ba3077e1f…` | POTENTIAL_CROSS_TX_MIRROR | B | 16.985783 | 24.208969 | 0x70ee6a7c…,0xddda35ed… |
| `0x1bac41668a90ecfa…` | REPEATED_POOL_ROUTE | B | 13.531504 | None |  |
| `0x5e4893d3f375fa67…` | REPEATED_POOL_ROUTE | B | 13.245812 | None |  |
| `0x559b6556decde2bc…` | POTENTIAL_CROSS_TX_MIRROR | C | 12.204012 | 18.112832 | 0x84472f5f…,0xcae68b09… |
| `0x6fd5174986867a8e…` | POTENTIAL_CROSS_TX_MIRROR | B | 11.469753 | 17.840027 | 0xff3a5ddb… |
| `0x6e8129d534ad09fa…` | POTENTIAL_CROSS_TX_MIRROR | B | 10.766236 | 12.178421 | 0xff78a773… |
| `0xb05eefd4676557fa…` | REPEATED_POOL_ROUTE | B | 7.295382 | None |  |

## Verdict inputs

- Verified evidence: frozen export rows + original classification/NET columns.
- Inferred linkage: cross-tx reverse pool swaps within ±3 blocks at ≤5% amount tolerance; repeated pool within a route.
