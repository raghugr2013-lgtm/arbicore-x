import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  RESEARCH_ACTIONS,
  displayMoney,
  displayScalar,
  orderedLegs,
  pageWindow,
} from "./ledgerFormat.mjs";

test("null is unavailable and zero stays zero", () => {
  assert.equal(displayScalar(null), "unavailable");
  assert.equal(displayScalar(undefined), "unavailable");
  assert.equal(displayScalar(0), "0");
  assert.equal(displayScalar(0.0), "0");
  assert.equal(displayMoney(0), "$0.00");
  assert.equal(displayMoney(-59.31), "-$59.31");
  assert.equal(displayMoney(null), "unavailable");
});

test("legs render in index order", () => {
  const legs = orderedLegs([
    { leg_index: 1, token_in: "WETH" },
    { leg_index: 0, token_in: "USDC" },
  ]);
  assert.deepEqual(legs.map((leg) => leg.token_in), ["USDC", "WETH"]);
});

test("pagination window", () => {
  const window = pageWindow(288, 2, 25);
  assert.equal(window.start, 25);
  assert.equal(window.end, 50);
  assert.equal(window.total, 288);
});

test("research actions do not include execution controls", () => {
  assert.deepEqual(RESEARCH_ACTIONS, ["Download Excel"]);
  const page = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../pages/LedgerExplorerPage.jsx"), "utf8");
  for (const word of ["resume", "broadcast", "kill", "sign", "wallet", "threshold"]) {
    assert.equal(page.toLowerCase().includes(word), false, word);
  }
  assert.equal(page.includes("RESEARCH_ACTIONS"), true);
});
