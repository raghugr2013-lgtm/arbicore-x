# G1.5 export manifest

- **export**: ArbiCore G1.5 MEV Scout evidence export
- **build_snapshot_utc**: 2026-10-08T22:16Z (REPORT.md generated 22:16 UTC)
- **exported_utc**: 2026-10-08T23:55Z
- **source_unchanged**: Files copied byte-for-byte from the 22:16 UTC build; source not modified, collection not restarted, ledger not regenerated.

## Windows
- base: 2026-10-08 00:00 -> 17:59 UTC, blocks 52314127-52346526, 18.0h (b00-b02)
- bsc: 2026-10-07 12:00 -> 2026-10-08 18:01 UTC, blocks 126248296-126488295, 30.0h (s04-s08)

## Winners QC (recomputed on export)
```
{
 "rows_by_chain_class": {
  "base|A": 1418,
  "base|B": 4252,
  "base|C": 57,
  "base|D": 560,
  "bnb|A": 1,
  "bnb|C": 12086,
  "bnb|D": 8933
 },
 "duplicate_tx_hash": 0,
 "transaction_status": {
  "base|1": 6287,
  "bnb|1": 21020
 }
}
```

## Notes
- out/qc.json is from the earlier 18:57 UTC build (12,312 rows) and was NOT re-run for this build; winners_qc above is recomputed on the exported file.
- BSC rows are NOT economically verified: untraced in-tx builder/validator payments cannot be reconstructed from public endpoints; BSC C/D rows carry upper bounds only.
- Base payout attribution: VERIFIED payees vs INFERRED payees are separate columns; use VERIFIED-only for decisions unless inferred wallets are confirmed.
- Segment bsc s02 (2026-10-07 00:00-06:00) finished after this build and is NOT included; s00,s01,s03 not yet analysed.
- Excluded: raw block/receipt chunks (data/, work/), RPC/collector state, .bak files, __pycache__. No credentials: only public RPC endpoints appear in code/gcpipe/chains.json and code/bsc/collect_bsc.py.

## Files

| path | role | bytes | rows | chain | window | sha256 |
|---|---|---|---|---|---|---|
| BASE_SEARCHER_CONTRACT_LEDGER_G1_5.jsonl | ESSENTIAL_BASE_REPLAY | 302007178 | 294238 | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `383ae172e5d526ed7a47ff30385ec36f718ddcd44bd15363c278cbc29e1d7538` |
| MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl | ESSENTIAL_BASE_REPLAY | 170083931 | 27307 | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `f525083f2ef218ce4532993c1dcc41e8807d0db68824408d9d4675d4ad871714` |
| PLAN.md | SUPPORTING_DOC | 5228 |  |  |  | `ce44529f15a842a3499fc70b1e11dcdf2fecb1594e2658a8d0a83a978f6a948d` |
| REPORT.md | ESSENTIAL_BASE_REPLAY | 34416 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `8d5813ec74fcce81a185b71b7935c7215a046fa018eefbad9f3250aa01e690fa` |
| code/auto_g15.sh | REPRODUCIBILITY_CODE | 246 |  |  |  | `895fc354be1fdf5cf2a632838864f9a6320b4fa4ecbeceeeeffedb9ea5544d8e` |
| code/bsc_wrap_corr.py | REPRODUCIBILITY_CODE | 2301 |  |  |  | `810c38216c9a996b1ea09da5e317da7b75c2995a59b5f8db21d38b412d75cf4c` |
| code/build_g15.py | REPRODUCIBILITY_CODE | 26896 |  |  |  | `4a9b2fce0aaf4043b9da7e6e1ee52672cac4c1debc392d498d7e9aeaae0afe40` |
| code/build_ledger.py | REPRODUCIBILITY_CODE | 12502 |  |  |  | `f8872a793977c90096a069f018c424ce51861f37d38af29e09bcdd99545ec968` |
| code/extra.py | REPRODUCIBILITY_CODE | 10886 |  |  |  | `1aca68d28e00fcfef30d8638333c84ed668661ca5026891c8f430739c9f36c6e` |
| code/make_report.py | REPRODUCIBILITY_CODE | 20603 |  |  |  | `51f9a09a79e8f574298291a5941244eeefaa4e08d1ce6edeec43d69e3c1d1946` |
| code/qc.py | REPRODUCIBILITY_CODE | 3557 |  |  |  | `fe9d86ce14a68cc0406f8b344985a8a84f44b6a4b130ea594aa6ed957ce8a1f8` |
| code/run_g15.sh | REPRODUCIBILITY_CODE | 3023 |  |  |  | `e588f07b0bbb74c7362d4d73452a1eb3c3e0833e549dcb8f6c6c3009b761c356` |
| code/run_seg.sh | REPRODUCIBILITY_CODE | 395 |  |  |  | `b4d5c07aa76decf674f5e97f1f5792910d0349c559621762301699097c934a27` |
| code/gcpipe/analyze.py | REPRODUCIBILITY_CODE | 59719 |  |  |  | `0782ccfdb2cbb3a976069226d2becfa1cb7e25bc0dbee099a5a4b6ec28d58dbe` |
| code/gcpipe/chains.json | REPRODUCIBILITY_CODE | 44694 |  |  |  | `d5127c8d9ae7af71a7f5364dd9a0669f49a49854acff14f1067976eadfbd91cd` |
| code/gcpipe/factory_labels.json | REPRODUCIBILITY_CODE | 2822 |  |  |  | `dcb9274c124c165128d267e6c834874af0fa179fd47a3ff69734e2fb61a655ff` |
| code/gcpipe/families_lib.py | REPRODUCIBILITY_CODE | 4877 |  |  |  | `54663ce4478bb9cc782150e1626c8b2c96eeb08f2f76a6e11af4a111a42bf2fb` |
| code/gcpipe/gc_common.py | REPRODUCIBILITY_CODE | 8353 |  |  |  | `3e59dcf27f6bffa10fb48681436dd87ec4e15a885a8bfd78d12f798da9c8673a` |
| code/gcpipe/v4addrs.py | REPRODUCIBILITY_CODE | 4841 |  |  |  | `9a09dc67f0e0c5b2e5ab5c3502dc7c7a6e2d7c54c07703aefa542f4f86d5ef24` |
| code/bsc/collect_bsc.py | REPRODUCIBILITY_CODE | 13497 |  |  |  | `4fe7d594a6680a38643866c2a98d3833b60a43503022d3272175b0b413503010` |
| code/bsc/inject_traces.py | REPRODUCIBILITY_CODE | 835 |  |  |  | `069e134a2488d42a7f20ba9c4a13d69765e77d9257c428c6dfcfcd6599bbafb7` |
| logs/analyze_base_b00.log | SUPPORTING_AUDIT | 1259 |  | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `09730df40d6f12bb347396909b0319c5cef354589cf317df7420825c30b432e9` |
| logs/analyze_base_b01.log | SUPPORTING_AUDIT | 1210 |  | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `82c5eecb52c0280f2d1da0763adb9598348f0d7791173708902ded8b5824320a` |
| logs/analyze_base_b02.log | SUPPORTING_AUDIT | 1483 |  | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `56ab045029aadaa62e5228fe5fe548fa4e4dab8e3e3600fa3a6abe047ca1dca0` |
| logs/analyze_bsc_s04.log | SUPPORTING_AUDIT | 1313 |  | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `ff1b20a87f56765f3c0e4f47bdbfcb51d88d0c66bc109f9dbe93ee8ac067500c` |
| logs/analyze_bsc_s05.log | SUPPORTING_AUDIT | 1205 |  | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `9b2de3d28f535f71ae21cf79789d921e36b25f00e70a5989f8a0c3b633b3e1eb` |
| logs/analyze_bsc_s06.log | SUPPORTING_AUDIT | 1118 |  | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `3d05823d81c6578e5ea675d8fbfdac5eda5737d62d1e8f94fa5f5fc5aae65256` |
| logs/analyze_bsc_s07.log | SUPPORTING_AUDIT | 1168 |  | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `99d9dfa1b6d6e9aebbbe490b3ff217469191cb4a58438dd44159af77cff64b8f` |
| logs/analyze_bsc_s08.log | SUPPORTING_AUDIT | 1318 |  | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `09e66dfb9fbc17b8093ee891c3cc7ee67e75755381ec778a158d1563af301adc` |
| segments/bsc/s07/.done | OPTIONAL_BSC_PARTIAL | 20 |  | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `873fd346e40345dd1d2018cdbcd21831f90f207c13c00cde83c8de8b322c9e81` |
| segments/bsc/s07/agg.parquet | OPTIONAL_BSC_PARTIAL | 46577658 | 1869930 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `62491edd459deb26add067645f2f72d12e241f6e9279ac363807238a767e1d80` |
| segments/bsc/s07/arbs.csv | OPTIONAL_BSC_PARTIAL | 87860016 | 60551 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `22d31edda6a4a9aa24739d2cd84d5a61dd37e1dba86e6b3c58a52c2aec3ede62` |
| segments/bsc/s07/blocks.parquet | OPTIONAL_BSC_PARTIAL | 521313 | 48000 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `0cbd135f236efa32ea540fddf58b9e9f4090ef3c66056c0bc250364c0a6e3d51` |
| segments/bsc/s07/classified_extra.jsonl | OPTIONAL_BSC_PARTIAL | 70974812 | 60551 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `ebc829f764b0eb324ca157821816d15a7ad4eafda173092b9f7f6a2f0b168e2c` |
| segments/bsc/s07/discovery.json | OPTIONAL_BSC_PARTIAL | 3302 |  | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `d3c608ec6ec2956f495b460382b22457f9926cbc42c3080e34e1b3c8da6868b0` |
| segments/bsc/s07/pricing.json | OPTIONAL_BSC_PARTIAL | 280 |  | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `240f079857c7f83305c8a39c82d8006a00e7f14bf84993925377a38152a5970f` |
| segments/bsc/s07/routes.csv | OPTIONAL_BSC_PARTIAL | 722999 | 3809 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `d916674079906623a8053a3b829415d29f46c3728b468c73793c836ee52c24d1` |
| segments/bsc/s07/searchers.csv | OPTIONAL_BSC_PARTIAL | 29036 | 84 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `484e4d23e132594f4aefe4e974749bc4e624248c40d4b20d3a7d27e1cead1cf5` |
| segments/bsc/s07/summary.json | OPTIONAL_BSC_PARTIAL | 8552 |  | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `9c21bf4ffae3540ed3c2ff54d928f5869268d59c1fb17a012941c5cbda29b9b4` |
| segments/bsc/s07/swaps.parquet | OPTIONAL_BSC_PARTIAL | 108313827 | 1673438 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `cf4d69407b0d861d730f224dca80f7f602e788d1687a5bb0ebb8e16f1ba07517` |
| segments/bsc/s07/tx.parquet | OPTIONAL_BSC_PARTIAL | 193813870 | 1702888 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `d6e5b36a17279ebddd55de60afd3ef18fce16928f20f22283b913078bb1f507c` |
| segments/bsc/s07/venues.csv | OPTIONAL_BSC_PARTIAL | 638 | 20 | bsc:s07 | 2026-10-08 06:00 -> 2026-10-08 12:00 UTC, blocks 126392296-126440295 | `aed0ff8270595a99890c172aee18368c763090b3ba7aa66ee71709f5b2742d4f` |
| segments/bsc/s04/.done | OPTIONAL_BSC_PARTIAL | 20 |  | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `ae4cbd1de207f0ad4cc072f9dc068bcc83ed2338b0ff535f2f5681aa6cca8098` |
| segments/bsc/s04/agg.parquet | OPTIONAL_BSC_PARTIAL | 48185217 | 1931155 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `cfa8c3b95485228eea05ee3c15fd21350ea0bf81078bf94de81d32b8779c458d` |
| segments/bsc/s04/arbs.csv | OPTIONAL_BSC_PARTIAL | 82016429 | 55296 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `9d2a41d8a07aafd9981f58f3dbee422592f890cee676f0d66e0ca2fd17aca7dc` |
| segments/bsc/s04/blocks.parquet | OPTIONAL_BSC_PARTIAL | 523985 | 48000 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `bb74dc83a405f966ebbb39056a5a20bc0c1c62441ec27d28d489b80908ff8d35` |
| segments/bsc/s04/classified_extra.jsonl | OPTIONAL_BSC_PARTIAL | 65999938 | 55296 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `620cdcfca5da8a6b47a2e4daa5f7513097726acb4d01dab0cf6dcef7e4e1acd6` |
| segments/bsc/s04/discovery.json | OPTIONAL_BSC_PARTIAL | 3313 |  | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `59ef17b9ebcfea7a0ed0159d3a4262d2b74a4ce0ebe6e03cf1eadb5d181facd1` |
| segments/bsc/s04/pricing.json | OPTIONAL_BSC_PARTIAL | 280 |  | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `cc16f3975565ee6c39c4e41d0b590f09748d2625c2aab8d253394a56a8bfd6c0` |
| segments/bsc/s04/routes.csv | OPTIONAL_BSC_PARTIAL | 1044161 | 5689 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `ed09f61ba4a6e76fa664169a3487e1dc4e51dff9069646bb268125fc7f65667a` |
| segments/bsc/s04/searchers.csv | OPTIONAL_BSC_PARTIAL | 30343 | 88 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `834075dc304898b5d38b6e2b8983e672ab15d994cc3dcfee84af3b9a6a58e963` |
| segments/bsc/s04/summary.json | OPTIONAL_BSC_PARTIAL | 8555 |  | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `85b42fb11d24f9ab38ca90db71fd4c3a371bd8f7c075c7cea3b002144feaf25c` |
| segments/bsc/s04/swaps.parquet | OPTIONAL_BSC_PARTIAL | 115408420 | 1722481 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `423cf860c6c1ea895a4654ba6aa5d1aa6c038407e462eccd9cf8aacdd1c92158` |
| segments/bsc/s04/tx.parquet | OPTIONAL_BSC_PARTIAL | 198629038 | 1738992 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `8fd7aad011a7637894768f06b911e7c89dbe7a76b5dd1b17ff69731ccafb4730` |
| segments/bsc/s04/venues.csv | OPTIONAL_BSC_PARTIAL | 608 | 19 | bsc:s04 | 2026-10-07 12:00 -> 2026-10-07 18:00 UTC, blocks 126248296-126296295 | `77ce2b892b01526b0c4f0e23958f20548c5db106a35a54df17f7ec8fed280ad0` |
| segments/bsc/cache/native_s02.json | OPTIONAL_BSC_PARTIAL | 493 |  | bsc | cache | `d4e9e3abc195c51cf596a89c62fcff39a3dda8baf4453e4440b5eabc916a1613` |
| segments/bsc/cache/native_s03.json | OPTIONAL_BSC_PARTIAL | 493 |  | bsc | cache | `f17f4d6ee18aa2cd0d734b98a8c3e8b8f0e2dd1d88070cca09b8565fd0b79b31` |
| segments/bsc/cache/native_s04.json | OPTIONAL_BSC_PARTIAL | 494 |  | bsc | cache | `fef2a520b140f5ca45b2da36b007925fb1a864102fce1c7fd09148ffb899bd09` |
| segments/bsc/cache/native_s05.json | OPTIONAL_BSC_PARTIAL | 494 |  | bsc | cache | `2c1150eb26e1894d785e24e3ab4e917d00ff5b0167787ac364cdd747fee6ce55` |
| segments/bsc/cache/native_s06.json | OPTIONAL_BSC_PARTIAL | 495 |  | bsc | cache | `40ae2f1f3ef128d226ee2a004ab340e294e56b18d55917ad455ba69ade69503f` |
| segments/bsc/cache/native_s07.json | OPTIONAL_BSC_PARTIAL | 495 |  | bsc | cache | `97f7b2a33d072977b2e411c37e0e326bcbe9058495e5ff523e76595c821e9127` |
| segments/bsc/cache/native_s08.json | OPTIONAL_BSC_PARTIAL | 440 |  | bsc | cache | `e0a677a2d669df33c01295fffcfee3cfd7af4f9655ce9fe705358356c8eba682` |
| segments/bsc/cache/pools.json | OPTIONAL_BSC_PARTIAL | 1876292 |  | bsc | cache | `cb99331dcfa527f12f21526cd33635b3ab2b5b9581218789184df2c5c3d26b1c` |
| segments/bsc/cache/prices_s02.json | OPTIONAL_BSC_PARTIAL | 734107 |  | bsc | cache | `c25f794c92a0cceca80ba836a7549e9027b6db2edd94488fec09e915d87e20a1` |
| segments/bsc/cache/prices_s03.json | OPTIONAL_BSC_PARTIAL | 857031 |  | bsc | cache | `4d3877ae8b9af7eb01b939865e99ebfe523065e6a60901d72da6469228aa6b26` |
| segments/bsc/cache/prices_s04.json | OPTIONAL_BSC_PARTIAL | 857127 |  | bsc | cache | `ec067d7a63ea3a56cbfb21233937688e5939785df329580748da6c4d5f2deeef` |
| segments/bsc/cache/prices_s05.json | OPTIONAL_BSC_PARTIAL | 605045 |  | bsc | cache | `4db0259adf83f0a888e4d7a407c288dc17f25f0ff68e59c2f943eca4d7e61df5` |
| segments/bsc/cache/prices_s06.json | OPTIONAL_BSC_PARTIAL | 638728 |  | bsc | cache | `9a32f1b42322057616dd60bb4293db02c70884371aae5078507fcf6323f1dbc0` |
| segments/bsc/cache/prices_s07.json | OPTIONAL_BSC_PARTIAL | 718540 |  | bsc | cache | `b9210f4dd9cb671a6dcd3445dc34ab61ecbab6c133ae46cc03c82c7b6ed5dd19` |
| segments/bsc/cache/prices_s08.json | OPTIONAL_BSC_PARTIAL | 1020037 |  | bsc | cache | `806412cb34e635fe4b27b3905e1cc3befb71fca6c4a9b84bd7507bf9454e5065` |
| segments/bsc/cache/traces_raw.json | OPTIONAL_BSC_PARTIAL | 76089 |  | bsc | cache | `47bd25c9200cf86ddb74f0b212f4f9059b3e556482be5167bdf6ea54dc6e1b95` |
| segments/bsc/cache/v4keys.json | OPTIONAL_BSC_PARTIAL | 958424 |  | bsc | cache | `8ce056a2d47090507e751f72f4485a5f26ad4aa0936c20fa780b94d26e4b0bdd` |
| segments/bsc/s06/.done | OPTIONAL_BSC_PARTIAL | 20 |  | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `a76041644e0f58d5f57c413c18f1fcce9739b90cfb328cbddb33641ce4269d66` |
| segments/bsc/s06/agg.parquet | OPTIONAL_BSC_PARTIAL | 39661034 | 1692997 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `c9d0831ce859919df8e65a4ea32ccaff9d77b3aaff0a42b5dd2bb79d1473e662` |
| segments/bsc/s06/arbs.csv | OPTIONAL_BSC_PARTIAL | 67476965 | 45650 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `aa010723b18b00aa11990cb598bfc975af6323cc1f8c796caea4ad5a06993617` |
| segments/bsc/s06/blocks.parquet | OPTIONAL_BSC_PARTIAL | 520819 | 48000 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `38c5cff34706d511e151510eaacc7a12ba97915675474626393cc499a07f1f86` |
| segments/bsc/s06/classified_extra.jsonl | OPTIONAL_BSC_PARTIAL | 54792777 | 45650 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `5e86530b7227ea4b4df232b7c9c1d75990225916718a0bf24b25771ba31b33ee` |
| segments/bsc/s06/discovery.json | OPTIONAL_BSC_PARTIAL | 3299 |  | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `c06607b2e6c46e614bc69aead905b71722f3a7af432d61d5775d5e27bb86854a` |
| segments/bsc/s06/pricing.json | OPTIONAL_BSC_PARTIAL | 280 |  | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `45c9198144a38136c3b21ffc13de4fc0d8c70ef469129fecf956c178801aec0e` |
| segments/bsc/s06/routes.csv | OPTIONAL_BSC_PARTIAL | 782654 | 4222 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `50560914fc3f53ec1939a645d081ead2a8c33dba3aa1736d074932af78d6d33a` |
| segments/bsc/s06/searchers.csv | OPTIONAL_BSC_PARTIAL | 31828 | 92 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `5b366841a69a9c96aafcc9389d395ba4d213f524695f06464a01def35d3d4e68` |
| segments/bsc/s06/summary.json | OPTIONAL_BSC_PARTIAL | 8284 |  | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `9df754b42e80a71dc8902b173eb52ad595aa54320bcd30035ac824e6cc3a4031` |
| segments/bsc/s06/swaps.parquet | OPTIONAL_BSC_PARTIAL | 91023767 | 1363346 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `8969513971bc582818530f4223b5c41f467ed2e6df0f658861e7763d5479877d` |
| segments/bsc/s06/tx.parquet | OPTIONAL_BSC_PARTIAL | 150747627 | 1312360 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `1f622f56b8f0750cf2bca1836ea19644dd51ba72f4bead58d4617d6e8f4a257c` |
| segments/bsc/s06/venues.csv | OPTIONAL_BSC_PARTIAL | 579 | 18 | bsc:s06 | 2026-10-08 00:00 -> 2026-10-08 06:00 UTC, blocks 126344296-126392295 | `990736852be10818a8eafaa098b93fbf936c2b3e2629299649d6d68f564a7678` |
| segments/bsc/s05/.done | OPTIONAL_BSC_PARTIAL | 20 |  | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `c38236e717ce1838327ffffd03f70620b35f7fe269566f0985ab1c8cb664b973` |
| segments/bsc/s05/agg.parquet | OPTIONAL_BSC_PARTIAL | 27051541 | 1255308 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `6e9b085d647f4d8ac76e05a2b5923075d8adb9ed40924f2aa9ca5b3e35ef32a4` |
| segments/bsc/s05/arbs.csv | OPTIONAL_BSC_PARTIAL | 44680824 | 30917 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `1019123a66f342dd591376fa4c6e58eb900c59585ebc097b6d2ee35bc90ad641` |
| segments/bsc/s05/blocks.parquet | OPTIONAL_BSC_PARTIAL | 516756 | 48000 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `0c2b7f80bb8aea84f699cef11fca7ec31cdf31095c1c5ec487d0d5f95ef4f083` |
| segments/bsc/s05/classified_extra.jsonl | OPTIONAL_BSC_PARTIAL | 36220581 | 30917 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `60a7496df26418dcf722ed5a73692d3f5ae292a97cef151ddd547ad6de06ab59` |
| segments/bsc/s05/discovery.json | OPTIONAL_BSC_PARTIAL | 3290 |  | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `3d7033e922e27bc42c38a7fed5c353861ffcb94527dc362f430e67dd05648f52` |
| segments/bsc/s05/pricing.json | OPTIONAL_BSC_PARTIAL | 279 |  | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `73a3b6c3877e2cc0e2c889de3a77c5756546faa7abddac64e5150cd8ef90ea83` |
| segments/bsc/s05/routes.csv | OPTIONAL_BSC_PARTIAL | 803413 | 4658 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `a9f5a1dad117eae0c7a530e34efe26579882aa183d187b864898d3d16f580fb1` |
| segments/bsc/s05/searchers.csv | OPTIONAL_BSC_PARTIAL | 27864 | 81 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `4f415e843fc004cc48b10cbd9bbf910fffcf81863e32898ae3f41d1bca8b6f2b` |
| segments/bsc/s05/summary.json | OPTIONAL_BSC_PARTIAL | 8358 |  | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `3e27effcff61bdb9c1e64137f99f6a1f313dcc6bf3102d60e1e41ded3f479942` |
| segments/bsc/s05/swaps.parquet | OPTIONAL_BSC_PARTIAL | 55760978 | 788313 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `61fddfa9963dc273aec25408ba231108dfb0a54a30257d1ab02c5f840b8628fc` |
| segments/bsc/s05/tx.parquet | OPTIONAL_BSC_PARTIAL | 86518137 | 766769 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `5c6cc642e994cb9f7ca5e7133333c881f94970d6711658948c315638e0d7cd4f` |
| segments/bsc/s05/venues.csv | OPTIONAL_BSC_PARTIAL | 652 | 21 | bsc:s05 | 2026-10-07 18:00 -> 2026-10-08 00:00 UTC, blocks 126296296-126344295 | `bc36c448b480d7c8603707a39188a09daab19175cc79a4e83ec5d5dbadfcb18b` |
| segments/bsc/s08/.done | OPTIONAL_BSC_PARTIAL | 20 |  | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `19f90aa22ab7277f17b583ecadfa41b7d508040d5bf90af33f27ee96e0f9fb41` |
| segments/bsc/s08/agg.parquet | OPTIONAL_BSC_PARTIAL | 52743420 | 2008969 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `6e660e70e6abfc3c011515a818e9ab11b13435ccdc90954a2a217f2198730968` |
| segments/bsc/s08/arbs.csv | OPTIONAL_BSC_PARTIAL | 131929324 | 82803 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `8674f503852e0564634de593cbab7f3a73f618432db8dc7cc9371c93f9df78e5` |
| segments/bsc/s08/blocks.parquet | OPTIONAL_BSC_PARTIAL | 809200 | 48000 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `4478accdcad1f13d53fcd54886e1cb0b91812492bd6c718da172ecee10530cc6` |
| segments/bsc/s08/classified_extra.jsonl | OPTIONAL_BSC_PARTIAL | 107488448 | 82803 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `4182e79075c4ea8bedbad637a33f083f883222fd0a7504b3b49b33131b53b551` |
| segments/bsc/s08/discovery.json | OPTIONAL_BSC_PARTIAL | 3342 |  | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `36eb90aaceaa5bdde7762432149d351702bb4a62304054f3477b0b6438f08fb5` |
| segments/bsc/s08/pricing.json | OPTIONAL_BSC_PARTIAL | 280 |  | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `a0dc628af1623e6346b02c13882e0bbb6fd0c6a3ed252a5d236da2c2335ac318` |
| segments/bsc/s08/routes.csv | OPTIONAL_BSC_PARTIAL | 2587326 | 13446 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `efb14aa29e0dc8cc8b2440d645ac793edbfc8d173d6d73177c538e8e36fba268` |
| segments/bsc/s08/searchers.csv | OPTIONAL_BSC_PARTIAL | 34748 | 100 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `fac17157fd057fece553ffd9e5a70786683fcf8b22ead2da56f7487c71275f38` |
| segments/bsc/s08/summary.json | OPTIONAL_BSC_PARTIAL | 8309 |  | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `c7fe7da4f83bff521ae0a5443da993a894464481c16015f581d60c36672ce5a5` |
| segments/bsc/s08/swaps.parquet | OPTIONAL_BSC_PARTIAL | 144220307 | 2158168 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `ceab1eba82785d77f9558d3f4f23764addbf181688f8591f4e22e850ccfa8560` |
| segments/bsc/s08/tx.parquet | OPTIONAL_BSC_PARTIAL | 236768368 | 2084717 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `c0f4a02932a1ba08e72e91b1b982a87b71ed03b9f2160be89779d178c88e2594` |
| segments/bsc/s08/venues.csv | OPTIONAL_BSC_PARTIAL | 622 | 19 | bsc:s08 | 2026-10-08 12:00 -> 2026-10-08 18:01 UTC, blocks 126440296-126488295 | `48fe93369150a1668f1de2e3ef9a63a81fed36bff32c0256eafc22744dce3263` |
| segments/base/b00/.done | SUPPORTING_AUDIT | 18 |  | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `581ded940c89e58673a24d713d556cada3a0cd6074e2c902bf0512af6ce546d5` |
| segments/base/b00/agg.parquet | SUPPORTING_AUDIT | 16188520 | 591744 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `7dd383fec24134c3215c32889ede3ac774b4bcb0eb3d1a309861729403ed3fdf` |
| segments/base/b00/arbs.csv | SUPPORTING_AUDIT | 39472034 | 25701 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `9d378108385498bb2a0b8fc169191ee1b2fc0a4ba0b008c175ebd1510afdabda` |
| segments/base/b00/blocks.parquet | SUPPORTING_AUDIT | 145306 | 10800 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `e2c3484aa633c07008071213511c3352d5d5bd64a25fe51b1dc92e8af9540b2c` |
| segments/base/b00/classified_extra.jsonl | SUPPORTING_AUDIT | 29233200 | 25701 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `31f1714daa90aafec155ce85de7bf9c66239fe5a9a40b8a6e3800ee04631fa39` |
| segments/base/b00/discovery.json | SUPPORTING_AUDIT | 3311 |  | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `43e1fc52cf96e419df7dd05682f178daeedd1910970559a4311ff4419e6c4859` |
| segments/base/b00/pricing.json | SUPPORTING_AUDIT | 280 |  | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `993d749869f026f4cd010b7a81e3db548ad93483686beb5d046d1509b2184f77` |
| segments/base/b00/routes.csv | SUPPORTING_AUDIT | 646027 | 3626 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `5c89bca3a39c4477edcb651db7c84250fdc8fa71df6289ff46aa09f0ce830504` |
| segments/base/b00/searchers.csv | SUPPORTING_AUDIT | 48763 | 135 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `c44bdd58c7590d2229d25f13f1c8ad3679125789778051be3982af1b8c4e59ba` |
| segments/base/b00/summary.json | SUPPORTING_AUDIT | 8406 |  | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `60181d93c177e225df9fbd95dffa0124d9a4311bad6d9356ade1da374e0bef5b` |
| segments/base/b00/swaps.parquet | SUPPORTING_AUDIT | 41601458 | 597515 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `7aaf7be9e4b0ed4d3e33bada2b19e42b78e61ab32416e82abe4e29f181e6cafd` |
| segments/base/b00/tx.parquet | SUPPORTING_AUDIT | 86899798 | 772770 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `45d24f2564feca95c3ffb3108ef090909fd29deac356b461918486e2990e80f3` |
| segments/base/b00/venues.csv | SUPPORTING_AUDIT | 788 | 25 | base:b00 | 2026-10-08 00:00 -> 2026-10-08 05:59 UTC, blocks 52314127-52324926 | `d2faef436717b991f1d248fdae125e7afc084724bf682ab8a1d1e002fb7393d1` |
| segments/base/cache/native_b00.json | SUPPORTING_AUDIT | 446 |  | base | cache | `48827c7b6230161589dc167ce117de9638e205001f9825da793acf726979a3b2` |
| segments/base/cache/native_b01.json | SUPPORTING_AUDIT | 445 |  | base | cache | `c6c47fdfd354f612a20d87e940d4302a2fe0f8693710acaa31c29ecd2f73a824` |
| segments/base/cache/native_b02.json | SUPPORTING_AUDIT | 443 |  | base | cache | `758f8fe94040fb51ba180e3c57cd3acf94e67436599b0825f3697dc5e8241d69` |
| segments/base/cache/pools.json | SUPPORTING_AUDIT | 293285 |  | base | cache | `dcc319881b1d130d66d5f2de5ff092411c4196f960355a50f76d9651d4827671` |
| segments/base/cache/prices_b00.json | SUPPORTING_AUDIT | 148238 |  | base | cache | `2d567be6066a91184e5b993d672cbe4905fb2c86e9e02e4957961538a6162fd5` |
| segments/base/cache/prices_b01.json | SUPPORTING_AUDIT | 163540 |  | base | cache | `dfb07403b69b7eafad3ecd2dc368eb89c07a45882602fb16db75c075aaecf7d0` |
| segments/base/cache/prices_b02.json | SUPPORTING_AUDIT | 271190 |  | base | cache | `0f98ace71eaeb3ea246c13bb17ef4410568d664c2df0564cc72af2cb49e91890` |
| segments/base/cache/traces_raw.json | SUPPORTING_AUDIT | 1925499 |  | base | cache | `d81feffe233d3b2022a5258263bb1b87d900b979bc1a0d343f4b031a3c920fe2` |
| segments/base/cache/v4keys.json | SUPPORTING_AUDIT | 948601 |  | base | cache | `4e48ea430e693934402b24bc53217fbba9b9bd2a045f12faab4135f60dba1d0e` |
| segments/base/b02/.done | SUPPORTING_AUDIT | 18 |  | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `409a451bd89ae1ac382d81c117031f0678b4b64a1b4384540a13c7ed76192614` |
| segments/base/b02/agg.parquet | SUPPORTING_AUDIT | 24217934 | 768495 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `2a0fc32af476ac211a89ade76c97cf8d21970d74846a486ef3a50d0a76584e13` |
| segments/base/b02/arbs.csv | SUPPORTING_AUDIT | 79791079 | 55480 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `bf57efc5f15a10fda6575f9034fb5c202d44677098091086e3d86d8cc05292cc` |
| segments/base/b02/blocks.parquet | SUPPORTING_AUDIT | 186745 | 10800 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `fd587e94ef367685dc1814a66240346dea5e91115e2c06681ef5819714b5cc71` |
| segments/base/b02/classified_extra.jsonl | SUPPORTING_AUDIT | 57503289 | 55480 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `84ba358162cc736d0bbcf96d8735c42e200d7d4efdfca0d1715c38d838199f07` |
| segments/base/b02/discovery.json | SUPPORTING_AUDIT | 1571 |  | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `60734100ce18397bafcebf27ef05515de398aaf8b3cba344714810d4d4649fda` |
| segments/base/b02/pricing.json | SUPPORTING_AUDIT | 281 |  | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `8a0d9c1dde2d14c29d89a8729c242614460a2e720426dc5a3827433acd727e02` |
| segments/base/b02/routes.csv | SUPPORTING_AUDIT | 1447755 | 8005 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `43703f7c4fab97a95eb677cd38f929ae75ab7a15a1584cf7764f73aaea266291` |
| segments/base/b02/searchers.csv | SUPPORTING_AUDIT | 71307 | 198 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `d58fd864d83da164d5b6b4a3945749eb707cfc06fc83d6b9a81dac49f81a09cf` |
| segments/base/b02/summary.json | SUPPORTING_AUDIT | 8835 |  | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `04198a63cc00e65aeb2ad014ae05da654bafbbdc89b3fc162c1576cb3882b4a2` |
| segments/base/b02/swaps.parquet | SUPPORTING_AUDIT | 65683758 | 943917 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `bee0742896d9ff278064210b45f55819d547bc5ea6d01eb7dc24e7157df008dd` |
| segments/base/b02/tx.parquet | SUPPORTING_AUDIT | 215201745 | 2161577 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `a5e3a6f922d5ac08c13c9abf9489b88c3405479dddad5cb201927c06146cc72d` |
| segments/base/b02/venues.csv | SUPPORTING_AUDIT | 732 | 22 | base:b02 | 2026-10-08 12:00 -> 2026-10-08 17:59 UTC, blocks 52335727-52346526 | `09ff6aff98a60716aefb662d735b613fe95d58f908e1dbe0558096d307d84f1a` |
| segments/base/b01/.done | SUPPORTING_AUDIT | 18 |  | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `1daf488e870806aac27ff336d20e2a42601185d8f8925fce523919e9f8e3a6a1` |
| segments/base/b01/agg.parquet | SUPPORTING_AUDIT | 17409660 | 600484 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `b1dd320328fc4c278021f1e105af34ef93b057ae30a5fa5dcab0203a729045e8` |
| segments/base/b01/arbs.csv | SUPPORTING_AUDIT | 59655532 | 39850 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `23ff2a690af0d5f1c473e4344749723bb3a2b2ac5f4c40221a0a3aca647f9bea` |
| segments/base/b01/blocks.parquet | SUPPORTING_AUDIT | 149823 | 10800 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `98cb6bb45e4dd21f1d3e90a50e43b23c4fbab6012364bf83a68882f1ecfd91bf` |
| segments/base/b01/classified_extra.jsonl | SUPPORTING_AUDIT | 42199661 | 39850 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `6a45cdbb48f7eabf9b633cd149b7d006141dbc9bc301b3b93d565e440c09a650` |
| segments/base/b01/discovery.json | SUPPORTING_AUDIT | 3318 |  | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `6fa91286163bca7af4e37a3124fa3ab3c5454c680b51dc333b7e52bd304384db` |
| segments/base/b01/pricing.json | SUPPORTING_AUDIT | 281 |  | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `8612365bfe16e067bf691b7573d21c9c0634be1373a5a41afdeb5a64a1665b74` |
| segments/base/b01/routes.csv | SUPPORTING_AUDIT | 655777 | 3635 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `c317ab650ff015428706e7ecb131f843865bf158b42b3c6e3d2b522463a96436` |
| segments/base/b01/searchers.csv | SUPPORTING_AUDIT | 48445 | 134 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `22066d27f387ca45da913fe85d61fe969884c46908c9cf358e94277c2229d488` |
| segments/base/b01/summary.json | SUPPORTING_AUDIT | 8673 |  | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `0416b7ee26e5b42c2445bdf5401882fa56f8e0d1471b6269988e5f9211b8814e` |
| segments/base/b01/swaps.parquet | SUPPORTING_AUDIT | 48440432 | 726619 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `5e9dcc15395cd3fdfa280d11fc015b1d7e4bc2100f09677ff0245d20eba527b4` |
| segments/base/b01/tx.parquet | SUPPORTING_AUDIT | 100249838 | 912725 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `7e7a089b762eaaf8f9e0db761b4b941d8c91dac985ae8639bcdde83b199cc9be` |
| segments/base/b01/venues.csv | SUPPORTING_AUDIT | 718 | 22 | base:b01 | 2026-10-08 06:00 -> 2026-10-08 11:59 UTC, blocks 52324927-52335726 | `b36f9e5c00e038aef415143c90e258f91e6296236edfbc48c56f44faa268e3e1` |
| out/bsc_builder_wrap_corr.json | OPTIONAL_BSC_PARTIAL | 1125 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `de4944464f33ed6ee196971b85137a1d60ed8dbef73bc8cd80962e828f3ef29c` |
| out/bsc_trace_stats.json | OPTIONAL_BSC_PARTIAL | 49 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `2615cdffd38a83618576ee7d813e14b9acf863cbeaaf20a4c541729b9286cf12` |
| out/identity_base.json | ESSENTIAL_BASE_REPLAY | 98180 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `eaf184237e96377a5e8aaa1ff429657499518da5feb6a2c908755c363a7a2c9b` |
| out/ledger_contracts.json | SUPPORTING_AUDIT | 5024 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `1f3d447a86cb8f7e297beff3ac5ab3d4a341f30a4bca84ff6d6a27218f6dc515` |
| out/owner_payees.json | ESSENTIAL_BASE_REPLAY | 8771 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `479b3222377ad7c9e37c6450fa0a503895cde582e0e0313101625d207d8e82bf` |
| out/payee_code.json | SUPPORTING_AUDIT | 4148 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `f0b43a3a1d4219bdb9f8eee3c097141b35c5032d784d7a9278310e8425c1c13d` |
| out/population_all.csv.gz | SUPPORTING_AUDIT | 29218910 | 328753 | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `ab40717b39de40f545b078075c076109287fc4652b0f5e5028bf1d121439d647` |
| out/qc.json | SUPPORTING_AUDIT | 460 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `62871bafebff2eb40cb552f3690c4be56ee4ba8c2e8205714f1c0769afbf3dfa` |
| out/registry.json | SUPPORTING_AUDIT | 18327 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `13a8ca3c779875d1ab14c3633707568eafed06c5904bcfa834d03720de8b362d` |
| out/report_extra.json | SUPPORTING_AUDIT | 7894 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `87a3bc8ce503a2c8f5743461508a30ab37443dba89ad45218d00bf9f269cea76` |
| out/segments.json | ESSENTIAL_BASE_REPLAY | 1562 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `7743848d822567e5f968e9d5904e5db38c7e203fa21838e3cd2806b1b4625449` |
| out/survival_base.json | ESSENTIAL_BASE_REPLAY | 80813 |  | base+bsc | Base 2026-10-08 00:00-17:59 UTC (18.0h); BSC 2026-10-07 12:00-2026-10-08 18:01 UTC (30.0h) | `ff93c6c328e9d0a79c3c26fcb3ee8bbfa6c4eaad69cd233d25234d8310df30a2` |
