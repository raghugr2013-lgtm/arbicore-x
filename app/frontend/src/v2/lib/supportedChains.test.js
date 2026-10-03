import {
  FALLBACK_SUPPORTED_CHAINS,
  resolveSupportedChains,
  unusedAllowlistChains,
  enableAllowlistedChain,
} from "./supportedChains";

describe("supportedChains — six-network dynamic Network Config", () => {
  test("fallback allowlist is exactly six including bnb", () => {
    expect(FALLBACK_SUPPORTED_CHAINS).toEqual([
      "base", "ethereum", "arbitrum", "optimism", "polygon", "bnb",
    ]);
    expect(FALLBACK_SUPPORTED_CHAINS).toContain("bnb");
    expect(FALLBACK_SUPPORTED_CHAINS).toHaveLength(6);
  });

  test("resolveSupportedChains prefers API payload", () => {
    const api = {
      supported_chains: ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"],
    };
    expect(resolveSupportedChains(api)).toEqual(api.supported_chains);
  });

  test("resolveSupportedChains filters unknown API chains", () => {
    const api = { supported_chains: ["base", "tron", "bnb"] };
    expect(resolveSupportedChains(api)).toEqual(["base", "bnb"]);
  });

  test("resolveSupportedChains falls back when API missing", () => {
    expect(resolveSupportedChains(null)).toEqual([...FALLBACK_SUPPORTED_CHAINS]);
    expect(resolveSupportedChains({})).toEqual([...FALLBACK_SUPPORTED_CHAINS]);
  });

  test("unusedAllowlistChains returns disabled only", () => {
    const unused = unusedAllowlistChains(
      FALLBACK_SUPPORTED_CHAINS,
      { base: true, ethereum: false, bnb: false },
    );
    expect(unused).toContain("bnb");
    expect(unused).toContain("ethereum");
    expect(unused).not.toContain("base");
  });

  test("enableAllowlistedChain enables bnb and seeds empty rpc row", () => {
    const form = {
      chains_enabled: { base: true, bnb: false },
      rpc_urls: { base: ["https://mainnet.base.org"] },
    };
    const r = enableAllowlistedChain(form, "bnb", FALLBACK_SUPPORTED_CHAINS);
    expect(r.ok).toBe(true);
    expect(r.form.chains_enabled.bnb).toBe(true);
    expect(r.form.rpc_urls.bnb).toEqual([]);
    // Original form untouched.
    expect(form.chains_enabled.bnb).toBe(false);
  });

  test("enableAllowlistedChain rejects duplicate enablement", () => {
    const form = { chains_enabled: { base: true }, rpc_urls: {} };
    const r = enableAllowlistedChain(form, "base", FALLBACK_SUPPORTED_CHAINS);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/already enabled/);
  });

  test("enableAllowlistedChain rejects unsupported chain", () => {
    const form = { chains_enabled: {}, rpc_urls: {} };
    const r = enableAllowlistedChain(form, "tron", FALLBACK_SUPPORTED_CHAINS);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/unsupported/);
  });

  test("FE pages no longer hard-code five-chain lists without bnb", () => {
    // Source-contract: Settings + FlashLoan must import shared allowlist.
    // eslint-disable-next-line global-require
    const fs = require("fs");
    const path = require("path");
    const settings = fs.readFileSync(
      path.join(__dirname, "../pages/SettingsPage.jsx"), "utf8");
    const flash = fs.readFileSync(
      path.join(__dirname, "../pages/FlashLoanOperatorPage.jsx"), "utf8");
    expect(settings).toContain("supportedChains");
    expect(settings).toContain("v2-settings-network-chain-${c}");
    expect(settings).toContain("Add Network");
    expect(settings).not.toMatch(
      /const CHAINS = \["base", "ethereum", "arbitrum", "optimism", "polygon"\];/,
    );
    expect(flash).toContain("FALLBACK_SUPPORTED_CHAINS");
    expect(flash).not.toMatch(
      /const CHAINS = \["base", "ethereum", "arbitrum", "optimism", "polygon"\];/,
    );
  });
});
