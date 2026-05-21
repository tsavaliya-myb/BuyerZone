interface StatCardProps {
  label: string;
  value: string | number;
  icon: any;
  iconColor?: string;
  iconBg?: string;
}

export default function StatCard({ 
  label, 
  value, 
  icon: Icon, 
  iconColor = 'text-primary', 
  iconBg = 'bg-primary-light' 
}: StatCardProps) {
  return (
    <div className="card card-hover p-4 flex items-center justify-between">
      <div>
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
          {label}
        </p>
        <h2 className="text-2xl font-bold text-slate-800 tracking-tight">
          {value}
        </h2>
      </div>
      <div className={`w-12 h-12 ${iconBg} rounded-xl flex items-center justify-center ${iconColor}`}>
        <Icon size={24} />
      </div>
    </div>
  );
}
