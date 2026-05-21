import { type ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  className?: string;
  actions?: ReactNode;
}

export default function Card({ children, title, subtitle, className = '', actions }: CardProps) {
  return (
    <div className={`card ${className}`}>
      {(title || actions) && (
        <div className="p-6 border-b border-slate-50 flex items-center justify-between">
          <div>
            {title && <h3 className="font-bold text-slate-800 tracking-tight">{title}</h3>}
            {subtitle && <p className="text-xs text-slate-400 font-medium mt-1">{subtitle}</p>}
          </div>
          {actions && <div>{actions}</div>}
        </div>
      )}
      <div className={title ? "p-0" : "p-6"}>
        {children}
      </div>
    </div>
  );
}
