// Exchange-specific onboarding instructions for creating READ-ONLY API keys.
// ArbiCore never trades, withdraws, or moves funds — grant ONLY read permission.
export const ONBOARDING = {
  xt: {
    name: "XT",
    url: "https://www.xt.com/en/accounts/api",
    steps: [
      "Log in to XT → Account → API Management",
      "Create API key — set permission to “Read Only” (uncheck Trade and Withdraw)",
      "No IP whitelist required for read access (optional: add this server's IP)",
      "Copy the AccessKey + SecretKey into the vault below",
    ],
  },
  mexc: {
    name: "MEXC",
    url: "https://www.mexc.com/user/openapi",
    steps: [
      "Log in to MEXC → Account → API Management",
      "Create key — tick ONLY “Account: read” (leave Trade and Withdraw unticked)",
      "Copy the Access Key + Secret Key into the vault",
    ],
  },
  gate: {
    name: "Gate",
    url: "https://www.gate.io/myaccount/api_key_manage",
    steps: [
      "Log in to Gate → API Keys → Create API Key",
      "Type: APIv4 — set Spot permission to “Read Only”, all others to None",
      "Copy the Key + Secret into the vault",
    ],
  },
  bitmart: {
    name: "BitMart",
    url: "https://www.bitmart.com/api-config/en-US",
    steps: [
      "Log in to BitMart → Account → API Management",
      "Create key — enter a Memo (required by BitMart, also paste it in the vault's memo field)",
      "Leave Trade and Withdraw permissions OFF (read access is default)",
      "Copy API Key + Secret + Memo into the vault",
    ],
  },
  coinstore: {
    name: "Coinstore",
    url: "https://www.coinstore.com/#/user/bindAuth/ApiManagement",
    steps: [
      "Log in to Coinstore → Account → API Management",
      "Create key — select read-only scope (no trade, no withdrawal)",
      "Copy API Key + Secret Key into the vault",
    ],
  },
};
