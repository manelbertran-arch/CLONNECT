import { ReactNode } from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

export function KPICard({
  title,
  value,
  change,
  changeLabel = 'vs semana anterior',
  icon,
  variant = 'default',
  size = 'md'
}: KPICardProps) {
  const getTrendIcon = () => {
    if (change === undefined || change === null) return null;
    if (change > 0) return <ArrowUpRight className="w-4 h-4" />;
    if (change < 0) return <ArrowDownRight className="w-4 h-4" />;
    return <Minus className="w-4 h-4" />;
  };

  const getTrendColor = () => {
    if (change === undefined || change === null) return 'text-gray-500';
    if (change > 0) return 'text-emerald-600';
    if (change < 0) return 'text-red-500';
    return 'text-gray-500';
  };

  const variantStyles: Record<string, string> = {
    default: 'bg-white border-gray-200 hover:border-gray-300',
    success: 'bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-200',
    warning: 'bg-gradient-to-br from-amber-50 to-yellow-50 border-amber-200',
    danger: 'bg-gradient-to-br from-red-50 to-rose-50 border-red-200'
  };

  const sizeStyles: Record<string, string> = {
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8'
  };

  const valueSizes: Record<string, string> = {
    sm: 'text-2xl',
    md: 'text-3xl',
    lg: 'text-4xl'
  };

  return (
    <div className={`rounded-2xl border transition-all duration-200 hover:shadow-lg cursor-default ${variantStyles[variant]} ${sizeStyles[size]}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          {title}
        </span>
        {icon && (
          <div className="p-2 bg-gray-100 rounded-lg text-gray-600">
            {icon}
          </div>
        )}
      </div>

      <div className="flex items-end justify-between">
        <div>
          <p className={`font-bold text-gray-900 ${valueSizes[size]}`}>
            {value}
          </p>
          {change !== undefined && change !== null && (
            <div className={`flex items-center mt-2 text-sm font-medium ${getTrendColor()}`}>
              {getTrendIcon()}
              <span className="ml-1">{change > 0 ? '+' : ''}{change.toFixed(1)}%</span>
              <span className="ml-2 text-gray-400 font-normal">{changeLabel}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
