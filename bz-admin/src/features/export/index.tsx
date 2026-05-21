import { Calendar, Users, Search, Play, FileDown, FileText, CheckCircle2, History, Download } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';

const recentExports = [
  { name: 'Q3_Electronics_Final.xlsx', time: 'Generated 2h ago', status: 'ready' },
  { name: 'Apparel_Bulk_Nov_Update.csv', time: 'Generated yesterday', status: 'history' }
];

export default function Export() {
  return (
    <MainLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">Export Data</h1>
        <p className="text-sm text-slate-400 font-medium mt-1">Generate comprehensive wholesale reports by filtering through our verified seller network.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* Main Configuration */}
        <div className="lg:col-span-8 space-y-8">
          <div className="card bg-white p-8 shadow-sm border border-slate-50">
            <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-8 flex items-center gap-2">
              <span className="w-1 h-1 bg-primary rounded-full"></span>
              Primary Configuration
            </h4>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">Analysis Date Range</label>
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50 rounded-xl cursor-pointer hover:bg-slate-100 transition-colors">
                  <span className="text-sm font-bold text-slate-700">Oct 12, 2023 — Nov 12, 2023</span>
                  <Calendar size={18} className="text-slate-400" />
                </div>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-3">Wholesale Seller</label>
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50 rounded-xl cursor-pointer hover:bg-slate-100 transition-colors">
                  <span className="text-sm font-bold text-slate-700">All Verified Sellers</span>
                  <Users size={18} className="text-slate-400" />
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">Specific Product Filter</label>
              <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input 
                  type="text" 
                  placeholder="Search by SKU, Name or Category..." 
                  className="w-full pl-12 pr-4 py-3.5 bg-slate-50 border-none rounded-xl text-sm font-medium outline-none"
                />
              </div>
            </div>
          </div>

          <div className="card bg-slate-100/30 p-8 border-2 border-dashed border-slate-100 relative overflow-hidden group">
            <h4 className="font-bold text-slate-800 text-sm mb-6">Export Format</h4>
            <div className="flex flex-wrap gap-3">
               <button className="px-5 py-2.5 bg-primary text-white text-[11px] font-black uppercase tracking-widest rounded-lg shadow-lg shadow-primary/20 transition-transform active:scale-95">
                  JSON (RAW)
               </button>
               <button className="px-5 py-2.5 bg-white text-slate-500 text-[11px] font-black uppercase tracking-widest rounded-lg hover:bg-white/80 transition-colors">
                  CSV
               </button>
               <button className="px-5 py-2.5 bg-white text-slate-500 text-[11px] font-black uppercase tracking-widest rounded-lg hover:bg-white/80 transition-colors">
                  PDF SUMMARY
               </button>
            </div>
            <div className="absolute -right-4 -bottom-4 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity">
               <FileText size={180} />
            </div>
          </div>
        </div>

        {/* Sidebar Actions */}
        <div className="lg:col-span-4 space-y-6">
           <div className="card bg-white p-8 shadow-sm border border-slate-50">
              <h4 className="font-bold text-slate-800 tracking-tight mb-1">Export Ready</h4>
              <p className="text-[11px] text-slate-400 font-bold mb-8">Estimated file size: <span className="text-slate-900">12.4 MB</span></p>
              
              <div className="space-y-3">
                 <button className="w-full flex items-center justify-center gap-2 py-4 bg-primary text-white rounded-xl font-bold transition-all hover:bg-primary-dark shadow-xl shadow-primary/10 group">
                    <Play size={18} fill="currentColor" />
                    Generate Report
                 </button>
                 <button className="w-full flex items-center justify-center gap-2 py-4 bg-slate-50 text-slate-600 rounded-xl font-bold transition-all hover:bg-slate-100">
                    <FileDown size={18} />
                    Download Excel (.xlsx)
                 </button>
              </div>
           </div>

           <div className="card bg-white p-6 shadow-sm border border-slate-50">
              <div className="flex items-center justify-between mb-8">
                 <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Recent Exports</h4>
                 <button className="text-primary text-[10px] font-bold uppercase underline underline-offset-4">View All</button>
              </div>
              <div className="space-y-6">
                 {recentExports.map((item, idx) => (
                   <div key={idx} className="flex items-center gap-4 group">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${item.status === 'ready' ? 'bg-primary/5 text-primary' : 'bg-slate-50 text-slate-400'}`}>
                         {item.status === 'ready' ? <CheckCircle2 size={18} /> : <History size={18} />}
                      </div>
                      <div className="flex-1">
                         <h5 className="text-[11px] font-bold text-slate-800 leading-none truncate max-w-[150px]">{item.name}</h5>
                         <p className="text-[10px] text-slate-400 font-bold mt-1.5">{item.time}</p>
                      </div>
                      <button className="text-slate-300 hover:text-primary transition-colors">
                         <Download size={16} />
                      </button>
                   </div>
                 ))}
              </div>
           </div>
        </div>

      </div>
    </MainLayout>
  );
}
