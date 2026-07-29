import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { AllocationPanel } from "@/components/portfolio/AllocationPanel";
import { BalancesPanel } from "@/components/portfolio/BalancesPanel";
import { DeployablePanel } from "@/components/portfolio/DeployablePanel";
import { HealthPanel } from "@/components/portfolio/HealthPanel";
import { ObservationPanel } from "@/components/portfolio/ObservationPanel";
import { OverviewBar } from "@/components/portfolio/OverviewBar";
import { QualityPanel } from "@/components/portfolio/QualityPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Portfolio() {
  const [balances, setBalances] = useState(null);
  const [deployable, setDeployable] = useState(null);
  const [allocation, setAllocation] = useState(null);
  const [health, setHealth] = useState(null);
  const [quality, setQuality] = useState(null);
  const [hours, setHours] = useState(24);
  const [refreshing, setRefreshing] = useState(false);

  const loadBalances = useCallback(() => {
    axios.get(`${API}/portfolio/balances`).then((r) => setBalances(r.data)).catch(() => {});
  }, []);

  const loadIntel = useCallback(() => {
    axios.get(`${API}/portfolio/deployable`).then((r) => setDeployable(r.data)).catch(() => {});
    axios.get(`${API}/portfolio/allocation`, { params: { hours: 24 } }).then((r) => setAllocation(r.data)).catch(() => {});
    axios.get(`${API}/health/exchanges`, { params: { hours: 24 } }).then((r) => setHealth(r.data)).catch(() => {});
  }, []);

  const loadQuality = useCallback(() => {
    axios.get(`${API}/quality`, { params: { hours } }).then((r) => setQuality(r.data)).catch(() => {});
  }, [hours]);

  useEffect(() => {
    loadBalances();
    loadIntel();
    const b = setInterval(loadBalances, 30000);
    const i = setInterval(loadIntel, 60000);
    return () => { clearInterval(b); clearInterval(i); };
  }, [loadBalances, loadIntel]);

  useEffect(() => {
    loadQuality();
    const q = setInterval(loadQuality, 60000);
    return () => clearInterval(q);
  }, [loadQuality]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const { data } = await axios.post(`${API}/portfolio/refresh`);
      data.ok ? toast.success(data.message) : toast.error(data.message);
      setTimeout(() => { loadBalances(); setRefreshing(false); }, 3000);
    } catch (e) {
      toast.error("Refresh failed");
      setRefreshing(false);
    }
  };

  return (
    <div className="px-4 pb-10 max-w-[1500px] mx-auto" data-testid="portfolio-page">
      <div className="flex flex-wrap items-center gap-3 py-3 border-b border-[#1f2a36] mb-4">
        <div className="font-mono text-sm font-bold tracking-wider">PORTFOLIO — REAL ACCOUNT INTELLIGENCE</div>
        <span className="text-[10px] font-mono text-[#6b7888]">read-only keys · no execution · no fund movement</span>
      </div>
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12"><OverviewBar data={balances} onRefresh={refresh} refreshing={refreshing} /></div>
        <div className="col-span-12 xl:col-span-7"><BalancesPanel data={balances} /></div>
        <div className="col-span-12 xl:col-span-5"><DeployablePanel data={deployable} /></div>
        <div className="col-span-12 xl:col-span-5"><AllocationPanel data={allocation} /></div>
        <div className="col-span-12 xl:col-span-7"><HealthPanel data={health} /></div>
        <div className="col-span-12"><QualityPanel data={quality} hours={hours} setHours={setHours} /></div>
        <div className="col-span-12"><ObservationPanel /></div>
      </div>
    </div>
  );
}
