import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Settings } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const EXCHANGES = ["xt", "mexc", "gate", "bitmart"];

const Field = ({ label, children }) => (
  <label className="block">
    <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</span>
    {children}
  </label>
);

export const RouteDialog = ({ route, onChanged }) => {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({});

  const init = () => setForm({
    buy_price: route?.manual_buy?.price ?? "",
    buy_qty: route?.manual_buy?.qty ?? "",
    buy_override: route?.manual_buy?.override ?? false,
    exit_exchange: route?.exit?.exchange ?? "xt",
    max_slippage_pct: route?.risk_profile?.max_slippage_pct ?? 1.0,
    participation_cap_pct: route?.risk_profile?.participation_cap_pct ?? 2.0,
    est_transfer_minutes: route?.risk_profile?.est_transfer_minutes ?? 30,
    fixed_fees_quote: route?.risk_profile?.fixed_fees_quote ?? 1.0,
    sim_deposit: route?.sim_config?.deposit_enabled ?? true,
    sim_base_price: route?.sim_config?.base_price ?? 0.00004,
    sim_vol: route?.sim_config?.daily_vol_pct ?? 18,
  });

  const save = async () => {
    try {
      await axios.patch(`${API}/routes/${route.id}`, {
        exit: { exchange: form.exit_exchange },
        manual_buy: {
          price: form.buy_price === "" ? null : parseFloat(form.buy_price),
          qty: form.buy_qty === "" ? null : parseFloat(form.buy_qty),
          override: form.buy_override,
        },
        risk_profile: {
          max_slippage_pct: parseFloat(form.max_slippage_pct),
          participation_cap_pct: parseFloat(form.participation_cap_pct),
          est_transfer_minutes: parseFloat(form.est_transfer_minutes),
          fixed_fees_quote: parseFloat(form.fixed_fees_quote),
        },
        sim_config: {
          deposit_enabled: form.sim_deposit,
          base_price: parseFloat(form.sim_base_price),
          daily_vol_pct: parseFloat(form.sim_vol),
        },
      });
      toast.success("Route configuration saved");
      setOpen(false);
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) init(); }}>
      <DialogTrigger asChild>
        <button data-testid="route-settings-btn" className="term-btn-secondary flex items-center gap-1.5">
          <Settings size={13} /> ROUTE CONFIG
        </button>
      </DialogTrigger>
      <DialogContent className="bg-[#10161e] border-[#1f2a36] text-[#c9d4e0] max-w-lg rounded-none">
        <DialogHeader>
          <DialogTitle className="font-mono tracking-wider text-[#ffb224]">ROUTE CONFIGURATION</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Field label="Exit exchange">
            <select data-testid="route-exit-exchange" value={form.exit_exchange} onChange={set("exit_exchange")} className="term-input w-full">
              {EXCHANGES.map((e) => <option key={e} value={e}>{e.toUpperCase()}</option>)}
            </select>
          </Field>
          <div />
          <Field label="Manual buy price (USDT)">
            <input data-testid="route-buy-price" value={form.buy_price} onChange={set("buy_price")}
                   disabled={!form.buy_override}
                   className={`term-input w-full ${!form.buy_override ? "opacity-40" : ""}`} />
          </Field>
          <Field label="Manual buy qty (asset)">
            <input data-testid="route-buy-qty" value={form.buy_qty} onChange={set("buy_qty")} className="term-input w-full" />
          </Field>
          <label className="col-span-2 flex items-center gap-2 text-xs font-mono text-[#c9d4e0] -mt-1">
            <input data-testid="route-buy-override-toggle" type="checkbox"
                   checked={form.buy_override} onChange={set("buy_override")} />
            <span>
              Manual price override
              <span className="text-[#6b7888]">
                {" "}— {form.buy_override ? "using manual price above" : "using LIVE PORTAL PRICE (sw-api/getInfo)"}
              </span>
            </span>
          </label>
          <Field label="Max slippage %">
            <input data-testid="route-max-slippage" value={form.max_slippage_pct} onChange={set("max_slippage_pct")} className="term-input w-full" />
          </Field>
          <Field label="Volume participation cap %">
            <input value={form.participation_cap_pct} onChange={set("participation_cap_pct")} className="term-input w-full" />
          </Field>
          <Field label="Est. transfer minutes">
            <input value={form.est_transfer_minutes} onChange={set("est_transfer_minutes")} className="term-input w-full" />
          </Field>
          <Field label="Fixed fees (quote)">
            <input value={form.fixed_fees_quote} onChange={set("fixed_fees_quote")} className="term-input w-full" />
          </Field>
        </div>
        <div className="border-t border-[#1f2a36] pt-3 mt-1">
          <div className="text-[9px] uppercase tracking-widest text-[#38bdf8] mb-2">Simulation scenario</div>
          <div className="grid grid-cols-3 gap-3 text-sm items-end">
            <Field label="Base price">
              <input value={form.sim_base_price} onChange={set("sim_base_price")} className="term-input w-full" />
            </Field>
            <Field label="Daily vol %">
              <input value={form.sim_vol} onChange={set("sim_vol")} className="term-input w-full" />
            </Field>
            <label className="flex items-center gap-2 text-xs font-mono pb-1.5">
              <input data-testid="sim-deposit-toggle" type="checkbox" checked={form.sim_deposit} onChange={set("sim_deposit")} />
              deposits enabled
            </label>
          </div>
        </div>
        <button data-testid="route-save-btn" onClick={save} className="term-btn-primary w-full mt-2">SAVE</button>
      </DialogContent>
    </Dialog>
  );
};
