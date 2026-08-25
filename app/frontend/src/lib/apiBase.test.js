import { computeApiBase, computeOrigin, apiUrl } from "./apiBase";

describe("apiBase normalization", () => {
  test("production absolute base -> single /api", () => {
    expect(computeApiBase("https://arbicorex.coinnike.com")).toBe("https://arbicorex.coinnike.com/api");
    expect(computeOrigin("https://arbicorex.coinnike.com")).toBe("https://arbicorex.coinnike.com");
  });

  test("production base with trailing slash", () => {
    expect(computeApiBase("https://arbicorex.coinnike.com/")).toBe("https://arbicorex.coinnike.com/api");
  });

  test("production base already ending in /api is not doubled", () => {
    expect(computeApiBase("https://arbicorex.coinnike.com/api")).toBe("https://arbicorex.coinnike.com/api");
    expect(computeApiBase("https://arbicorex.coinnike.com/api/")).toBe("https://arbicorex.coinnike.com/api");
    expect(computeOrigin("https://arbicorex.coinnike.com/api")).toBe("https://arbicorex.coinnike.com");
  });

  test("same-origin /api base -> /api (no /api/api)", () => {
    expect(computeApiBase("/api")).toBe("/api");
    expect(computeApiBase("/api/")).toBe("/api");
    expect(computeOrigin("/api")).toBe("");
  });

  test("empty base -> same-origin /api", () => {
    expect(computeApiBase("")).toBe("/api");
    expect(computeApiBase(undefined)).toBe("/api");
    expect(computeOrigin("")).toBe("");
  });

  test("apiUrl joins with exactly one /api and one slash", () => {
    // absolute
    expect(`${computeApiBase("https://h")}/arbicore/opportunities`).toBe("https://h/api/arbicore/opportunities");
    // same-origin: no /api/api duplication
    const base = computeApiBase("/api");
    expect(`${base}/arbicore/opportunities`).toBe("/api/arbicore/opportunities");
    expect(`${base}/arbicore/opportunities`.includes("/api/api")).toBe(false);
  });

  test("origin + own /api path never doubles under same-origin", () => {
    // OpsCenter pattern: `${BACKEND_ORIGIN}${'/api/...'}`
    expect(`${computeOrigin("/api")}/api/arbicore/live/status`).toBe("/api/arbicore/live/status");
    expect(`${computeOrigin("https://h")}/api/arbicore/live/status`).toBe("https://h/api/arbicore/live/status");
    expect(`${computeOrigin("/api")}/api/arbicore/live/status`.includes("/api/api")).toBe(false);
  });

  test("apiUrl helper", () => {
    expect(apiUrl("/arbicore/x")).toBe(`${computeApiBase(process.env.REACT_APP_BACKEND_URL)}/arbicore/x`);
    expect(apiUrl("arbicore/x").includes("/api/api")).toBe(false);
  });
});
