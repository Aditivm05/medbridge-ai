import React from 'react';

interface SimulationBadgeProps {
  label?: string;
  size?: 'sm' | 'md';
}

export const SimulationBadge: React.FC<SimulationBadgeProps> = ({ label = 'DEMO / SIMULATED', size = 'sm' }) => {
  const sizeClasses = size === 'sm' ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2.5 py-1';
  return (
    <span
      className={`inline-flex items-center font-mono font-bold uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-300 rounded shadow-xs select-none ${sizeClasses}`}
      title="This component represents simulated synthetic demo data for the hackathon MVP"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mr-1 animate-pulse" />
      {label}
    </span>
  );
};
