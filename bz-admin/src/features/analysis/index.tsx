import { BarChart3, RotateCcw, Upload, ChevronRight } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';

const matrixData = [
  {
    initial: 'G',
    name: 'Global Distribution Co.',
    contact: '+1 (555) 092-8821',
    price: '$98.00',
    tag: 'LOWEST',
    tagColor: 'text-blue-600 bg-blue-50',
    date: 'Oct 12, 2023'
  },
  {
    initial: 'L',
    name: 'Lumina Wholesale',
    contact: '+1 (555) 212-0045',
    price: '$102.50',
    tag: null,
    date: 'Oct 14, 2023'
  },
  {
    initial: 'A',
    name: 'Atlas Logistics Group',
    contact: '+1 (555) 341-9980',
    price: '$118.00',
    tag: null,
    date: 'Oct 11, 2023'
  },
  {
    initial: 'P',
    name: 'Prime Sourcing Inc.',
    contact: '+1 (555) 882-1212',
    price: '$145.00',
    tag: 'HIGHEST',
    tagColor: 'text-red-600 bg-red-50',
    date: 'Oct 15, 2023'
  }
];

const history = [
  { name: 'Smart Watch V2', time: 'Analyzed 2h ago', image: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=40&h=40&fit=crop' },
  { name: 'Bass Pro Headphones', time: 'Analyzed 5h ago', image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=40&h=40&fit=crop' }
];

export default function Analysis() {
  return (
    <MainLayout>
      <div className="mb-6">
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Analysis Details</h1>
      </div>

      {/* Main Content Grid */}
      <div className="space-y-4">
        
        {/* Row 1: Product Header */}
        <div className="card bg-white py-4 px-8 flex flex-col md:flex-row items-center gap-8 shadow-sm border border-slate-50">
          <div className="w-20 h-20 rounded-2xl overflow-hidden shadow-md">
            <img 
              src="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=100&h=100&fit=crop" 
              className="w-full h-full object-cover" 
              alt="Product"
            />
          </div>
          <div className="flex-1 text-center md:text-left">
             <p className="text-[10px] font-bold text-primary uppercase tracking-widest mb-1 underline decoration-2 underline-offset-4">Product Identity</p>
             <h2 className="text-2xl font-extrabold text-slate-800 tracking-tight mb-1.5">Performance Series X1 - Crimson</h2>
             <div className="flex items-center justify-center md:justify-start gap-6 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                <span className="flex items-center gap-2"><BarChart3 size={14}/> SKU-88291-R</span>
                <span className="flex items-center gap-2">Athletics</span>
             </div>
          </div>
          <div className="md:border-l border-slate-100 pl-10 text-right hidden md:block min-w-fit">
             <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Avg. Price</p>
             <h3 className="text-3xl font-extrabold text-slate-800 tracking-tighter">$114.50</h3>
          </div>
        </div>

        {/* Row 2: Chart + Search History */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
          <div className="lg:col-span-9 card bg-white p-8 shadow-sm border border-slate-50 flex flex-col">
            <div className="mb-12">
               <h3 className="font-extrabold text-slate-800 text-lg tracking-tight">Seller Price Comparison</h3>
               <p className="text-xs text-slate-400 font-semibold mt-1">Real-time market distribution across 6 verified vendors</p>
            </div>
            <div className="flex-1 flex flex-col justify-end">
              <div className="flex justify-around items-end gap-2 px-6 h-48">
                {[60, 80, 45, 90, 70, 55].map((h, i) => (
                  <div key={i} className="w-full max-w-[40px] bg-slate-50 rounded-t-xl relative group h-full">
                    <div className="absolute inset-x-0 bottom-0 bg-primary/10 group-hover:bg-primary/20 transition-all rounded-t-xl" style={{ height: `${h}%` }}></div>
                  </div>
                ))}
              </div>
              <div className="flex justify-around text-[9px] font-bold text-slate-400 uppercase tracking-widest pt-8 pb-4">
                <span>Lumina</span>
                <span>Global</span>
                <span>PeakWhl</span>
                <span>Atlas</span>
                <span>Direct</span>
                <span>Prime</span>
              </div>
            </div>
          </div>

          <div className="lg:col-span-3 card bg-white p-6 shadow-sm border border-slate-50">
            <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-8">Search History</h4>
            <div className="space-y-6">
               {history.map((item, idx) => (
                 <button key={idx} className="w-full flex items-center gap-5 group text-left">
                    <div className="w-12 h-12 rounded-xl overflow-hidden border border-slate-100 flex-shrink-0 bg-slate-50">
                       <img src={item.image} className="w-full h-full object-cover group-hover:scale-110 transition-transform opacity-90" />
                    </div>
                    <div className="flex-1">
                       <h5 className="text-xs font-bold text-slate-800 leading-tight mb-1">{item.name}</h5>
                       <p className="text-[10px] text-slate-400 font-bold">{item.time}</p>
                    </div>
                    <ChevronRight size={18} className="text-slate-300 group-hover:text-primary group-hover:translate-x-1 transition-all" />
                 </button>
               ))}
            </div>
          </div>
        </div>

        {/* Row 3: Matrix + Upload */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          <div className="lg:col-span-9 card bg-white overflow-hidden shadow-sm border border-slate-50">
            <div className="p-6 border-b border-slate-50 flex items-center justify-between">
               <h3 className="font-extrabold text-slate-800 tracking-tight">Price Comparison Matrix</h3>
               <button className="text-primary text-[10px] font-bold uppercase tracking-widest flex items-center gap-2 hover:bg-slate-50 px-3 py-2 rounded-lg transition-colors">
                  <RotateCcw size={14} /> Refresh Data
               </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left min-w-[800px]">
                <thead>
                  <tr className="bg-[#fcfdff] border-b border-slate-50 uppercase text-[9px] font-bold text-slate-400 tracking-widest">
                    <th className="px-8 py-5">Seller Name</th>
                    <th className="px-8 py-5">Contact Info</th>
                    <th className="px-8 py-5">Pricing</th>
                    <th className="px-8 py-5 text-center">Last Verified</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {matrixData.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-8 py-5">
                         <div className="flex items-center gap-4">
                            <div className="w-9 h-9 rounded-xl bg-slate-50 flex items-center justify-center text-[10px] font-bold text-primary border border-slate-100">
                               {row.initial}
                            </div>
                            <span className="text-sm font-bold text-slate-700">{row.name}</span>
                         </div>
                      </td>
                      <td className="px-8 py-5 text-sm text-slate-500 font-semibold">
                         {row.contact}
                      </td>
                      <td className="px-8 py-5">
                         <div className="text-sm font-bold text-slate-800 leading-none">{row.price}</div>
                         {row.tag && (
                           <div className={`inline-block text-[9px] font-black uppercase mt-1.5 px-2 py-0.5 rounded ${row.tagColor}`}>
                              {row.tag}
                           </div>
                         )}
                      </td>
                      <td className="px-8 py-5 text-center text-[11px] font-bold text-slate-400">
                         {row.date}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="lg:col-span-3 card bg-slate-100/50 p-6 border-2 border-dashed border-slate-200">
             <h4 className="font-bold text-slate-800 text-sm mb-1 tracking-tight">Upload New Image</h4>
             <p className="text-[10px] text-slate-400 font-bold mb-8">Start a new analysis instantly</p>
             <div className="card bg-white rounded-2xl p-8 flex flex-col items-center justify-center border border-slate-200 border-dashed hover:border-primary/50 transition-colors cursor-pointer group">
                <div className="bg-primary/5 p-3 rounded-xl mb-4 group-hover:bg-primary/10 transition-colors">
                   <Upload className="text-primary" size={20} />
                </div>
                <span className="text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">Drag & Drop</span>
             </div>
          </div>
        </div>

      </div>
    </MainLayout>
  );
}
