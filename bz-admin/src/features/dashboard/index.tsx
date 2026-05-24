import { useEffect, useState } from 'react';
import { LayoutDashboard, Users } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import StatCard from './components/StatCard';
import RecentlyAnalyzed from './components/RecentlyAnalyzed';
import { dashboardService, type DashboardStats } from '@/services/dashboard';
import { messagingService, type TelegramStatusResponse, type WhatsappStatusResponse } from '@/services/messaging';
import { Send, MessageCircle, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [tgStatus, setTgStatus] = useState<TelegramStatusResponse | null>(null);
  const [waStatus, setWaStatus] = useState<WhatsappStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsData, tgData, waData] = await Promise.all([
          dashboardService.getStats(),
          messagingService.getTelegramStatus().catch(() => null),
          messagingService.getWhatsappStatus().catch(() => null),
        ]);
        setStats(statsData);
        setTgStatus(tgData);
        setWaStatus(waData);
      } catch (error) {
        console.error("Failed to fetch dashboard data", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  return (
    <MainLayout>
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Market Overview</h1>
          <p className="text-slate-500 font-medium mt-1">Real-time analysis of your wholesale ecosystem.</p>
        </div>
        <div className="bg-white/50 backdrop-blur px-4 py-2 rounded-lg border border-slate-100 flex items-center gap-3">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Live</span>
        </div>
      </div>

      {/* Connection Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Telegram Status */}
        <div className="bg-white rounded-[24px] p-6 border border-slate-100 shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg transition-all ${
              loading 
                ? 'bg-slate-50 text-slate-300 animate-pulse' 
                : tgStatus?.connected 
                  ? 'bg-[#229ED9] shadow-[#229ED9]/20 text-white' 
                  : 'bg-slate-100 text-slate-400'
            }`}>
              <Send size={24} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest">Telegram Status</h3>
              <div className="flex items-center gap-2 mt-1">
                {loading ? (
                  <div className="flex items-center gap-2">
                    <Loader2 size={16} className="text-primary animate-spin" />
                    <span className="text-slate-400 text-sm font-medium">Checking connection...</span>
                  </div>
                ) : tgStatus?.connected ? (
                  <>
                    <CheckCircle2 size={16} className="text-emerald-500" />
                    <span className="font-bold text-slate-800">{tgStatus.display_name || 'Connected'}</span>
                    <span className="text-slate-400 text-sm border-l border-slate-200 pl-2 ml-1">+{tgStatus.phone}</span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={16} className="text-slate-400" />
                    <span className="font-bold text-slate-500">Disconnected</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* WhatsApp Status */}
        <div className="bg-white rounded-[24px] p-6 border border-slate-100 shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg transition-all ${
              loading 
                ? 'bg-slate-50 text-slate-300 animate-pulse' 
                : waStatus?.state === 'connected' 
                  ? 'bg-[#25D366] shadow-[#25D366]/20 text-white' 
                  : 'bg-slate-100 text-slate-400'
            }`}>
              <MessageCircle size={24} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest">WhatsApp Status</h3>
              <div className="flex items-center gap-2 mt-1">
                {loading ? (
                  <div className="flex items-center gap-2">
                    <Loader2 size={16} className="text-primary animate-spin" />
                    <span className="text-slate-400 text-sm font-medium">Checking connection...</span>
                  </div>
                ) : waStatus?.state === 'connected' ? (
                  <>
                    <CheckCircle2 size={16} className="text-emerald-500" />
                    <span className="font-bold text-slate-800">{waStatus.display_name || 'Connected'}</span>
                    <span className="text-slate-400 text-sm border-l border-slate-200 pl-2 ml-1">+{waStatus.phone}</span>
                  </>
                ) : (
                  <>
                    <AlertCircle size={16} className="text-slate-400" />
                    <span className="font-bold text-slate-500 capitalize">{waStatus?.state || 'Disconnected'}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <StatCard 
          label="Total Products" 
          value={loading ? "..." : (stats?.total_products?.toLocaleString() || "0")} 
          icon={LayoutDashboard} 
          iconColor="text-blue-600"
          iconBg="bg-blue-50"
        />
        <StatCard 
          label="Total Sellers" 
          value={loading ? "..." : (( (stats?.total_wholesalers || 0) + (stats?.active_chats || 0) ).toLocaleString())} 
          icon={Users} 
          iconColor="text-purple-600"
          iconBg="bg-purple-50"
        />
      </div>

      {/* Main Table Section */}
      <RecentlyAnalyzed totalProducts={stats?.total_products || 0} />
    </MainLayout>
  );
}
