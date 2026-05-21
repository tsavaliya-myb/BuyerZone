import MainLayout from '@/components/layout/MainLayout';
import { Bell, Check, Clock, Trash2, Info, AlertTriangle, MessageSquare, Filter } from 'lucide-react';
import { useState } from 'react';

const notificationsData = [
  {
    id: 1,
    title: 'Price Drop Alert',
    description: 'The price for "Premium Ceramic Vase" has dropped by 15% from your watched seller.',
    time: '2 hours ago',
    type: 'price',
    unread: true,
  },
  {
    id: 2,
    title: 'New Seller Verified',
    description: 'Expert Craftsmen Ltd. has completed the verification process and is now available for sourcing.',
    time: '5 hours ago',
    type: 'system',
    unread: true,
  },
  {
    id: 3,
    title: 'Analysis Complete',
    description: 'Your image search analysis for "Modern Nordic Chair" is ready for review.',
    time: 'Yesterday',
    type: 'analysis',
    unread: false,
  },
  {
    id: 4,
    title: 'System Maintenance',
    description: 'The platform will undergo scheduled maintenance on Sunday from 02:00 AM to 04:00 AM UTC.',
    time: '2 days ago',
    type: 'alert',
    unread: false,
  },
  {
    id: 5,
    title: 'Inquiry Response',
    description: 'You have received a new message from "Global Sourcing Co." regarding your inquiry.',
    time: '3 days ago',
    type: 'message',
    unread: false,
  },
];

const getIcon = (type: string) => {
  switch (type) {
    case 'price': return <Clock className="text-blue-500" size={16} />;
    case 'system': return <Check className="text-emerald-500" size={16} />;
    case 'analysis': return <Bell className="text-purple-500" size={16} />;
    case 'alert': return <AlertTriangle className="text-amber-500" size={16} />;
    case 'message': return <MessageSquare className="text-primary" size={16} />;
    default: return <Info className="text-slate-400" size={16} />;
  }
};

export default function Notifications() {
  const [activeTab, setActiveTab] = useState('all');

  return (
    <MainLayout>
      <div className="max-w-5xl mx-auto">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Notification Center</h1>
            <p className="text-slate-500 font-medium mt-1">Manage your alerts and stay updated with market shifts.</p>
          </div>
          
          <div className="flex items-center gap-3">
            <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50 transition-all shadow-sm">
              <Check size={14} />
              MARK ALL AS READ
            </button>
            <button className="p-2.5 bg-white border border-slate-200 rounded-xl text-slate-400 hover:text-slate-600 transition-all shadow-sm">
              <Filter size={18} />
            </button>
          </div>
        </div>

        {/* Filters/Tabs */}
        <div className="flex items-center gap-1 mb-6 p-1 bg-slate-200/50 backdrop-blur-sm rounded-2xl w-fit">
          {['all', 'unread', 'archived'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2 rounded-xl text-xs font-extrabold uppercase tracking-widest transition-all ${
                activeTab === tab 
                ? 'bg-white text-primary shadow-sm' 
                : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Notifications List */}
        <div className="bg-white rounded-3xl border border-slate-100 shadow-xl shadow-slate-200/40 overflow-hidden">
          <div className="divide-y divide-slate-50">
            {notificationsData.map((notif) => (
              <div 
                key={notif.id} 
                className={`group p-5 md:p-6 flex gap-5 transition-all cursor-pointer relative ${
                  notif.unread ? 'bg-primary/[0.02]' : 'hover:bg-slate-50/50'
                }`}
              >
                {/* Unread Indicator Dot */}
                {notif.unread && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary"></div>
                )}

                {/* Icon Container */}
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 transition-transform group-hover:scale-105 ${
                  notif.unread ? 'bg-primary/10 shadow-inner' : 'bg-slate-50 border border-slate-100'
                }`}>
                  {getIcon(notif.type)}
                </div>
                
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between mb-1.5">
                    <div>
                      <h3 className={`text-[15px] font-bold tracking-tight mb-0.5 ${
                        notif.unread ? 'text-slate-900' : 'text-slate-600 text-opacity-90'
                      }`}>
                        {notif.title}
                        {notif.unread && <span className="ml-2 inline-block w-1.5 h-1.5 bg-primary rounded-full"></span>}
                      </h3>
                      <p className="text-[13px] text-slate-500 leading-relaxed font-medium">
                        {notif.description}
                      </p>
                    </div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1 tabular-nums">
                      {notif.time}
                    </span>
                  </div>
                  
                  {/* Actions (visible on hover or if unread) */}
                  <div className="mt-4 flex items-center gap-4">
                    <button className="text-[11px] font-extrabold text-primary uppercase tracking-widest hover:text-primary-dark flex items-center gap-1.5 group/btn border-b border-transparent hover:border-primary pb-0.5 transition-all">
                      View Details
                    </button>
                    {!notif.unread && (
                      <button className="text-[11px] font-extrabold text-slate-400 uppercase tracking-widest hover:text-slate-600 transition-colors">
                        Archive
                      </button>
                    )}
                    {notif.unread && (
                      <button className="text-[11px] font-extrabold text-slate-400 uppercase tracking-widest hover:text-slate-600 transition-colors">
                        Dismiss
                      </button>
                    )}
                  </div>
                </div>

                {/* Delete Button (hover only) */}
                <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-start">
                   <button className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all">
                     <Trash2 size={16} />
                   </button>
                </div>
              </div>
            ))}
          </div>
          
          {/* Footer Action */}
          <div className="p-6 bg-slate-50/30 flex justify-center border-t border-slate-50">
            <button className="px-8 py-3 bg-white border border-slate-200 rounded-2xl text-[11px] font-extrabold text-slate-500 hover:text-primary hover:border-primary/30 transition-all uppercase tracking-[0.2em] shadow-sm active:scale-95">
              Load Older Notifications
            </button>
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
