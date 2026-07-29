import { useState } from "react";
import { SecuritySection } from "@/components/settings/SecuritySection";
import { TelegramSection } from "@/components/settings/TelegramSection";
import { VaultSection } from "@/components/settings/VaultSection";

const TABS = [
  { id: "vault", label: "API KEY VAULT" },
  { id: "alerts", label: "TELEGRAM ALERTS" },
  { id: "security", label: "SECURITY" },
];

export default function Settings() {
  const [tab, setTab] = useState("vault");
  return (
    <div className="px-4 pb-10 max-w-[1100px] mx-auto" data-testid="settings-page">
      <div className="flex flex-wrap items-center gap-3 py-3 border-b border-[#1f2a36] mb-4">
        <div className="font-mono text-sm font-bold tracking-wider">SETTINGS</div>
        <span className="text-[10px] font-mono text-[#6b7888]">read-only intelligence — no execution capability exists in this build</span>
        <div className="flex-1" />
        {TABS.map((t) => (
          <button key={t.id} data-testid={`settings-tab-${t.id}`} onClick={() => setTab(t.id)}
                  className={`font-mono text-[10px] font-bold tracking-wider px-3 py-1.5 border transition-colors ${
                    tab === t.id ? "border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10"
                                 : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "vault" && <VaultSection />}
      {tab === "alerts" && <TelegramSection />}
      {tab === "security" && <SecuritySection />}
    </div>
  );
}
