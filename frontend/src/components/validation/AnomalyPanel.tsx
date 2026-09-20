import React from 'react';
import { AnomalySignal } from '../../types/api.ts';
import { AlertCircle, AlertTriangle, Info, CheckCircle2 } from 'lucide-react';

interface AnomalyPanelProps {
  anomalies: AnomalySignal[];
}

export const AnomalyPanel: React.FC<AnomalyPanelProps> = ({ anomalies }) => {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="bg-[#222428] border border-[#2d3034] rounded-lg p-3 text-xs text-[#a09f99] flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-[#4e8a5b]" />
        <span>No cadastral anomaly findings detected.</span>
      </div>
    );
  }

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center justify-between pb-1">
        <span className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">
          Cadastral Anomaly Findings ({anomalies.length})
        </span>
        <span className="text-[11px] text-[#a09f99]/80 italic">Advisory Anomalies</span>
      </div>

      <div className="space-y-2">
        {anomalies.map(sig => {
          const isWarning = sig.severity === 'WARNING';
          const isCritical = sig.severity === 'CRITICAL';

          return (
            <div
              key={sig.id}
              className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                isCritical
                  ? 'bg-[#b84d47]/10 border-[#b84d47]/30 text-[#f4f3ef]'
                  : isWarning
                  ? 'bg-[#c98a2c]/10 border-[#c98a2c]/30 text-[#f4f3ef]'
                  : 'bg-[#222428] border-[#2d3034] text-[#f4f3ef]'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-1.5 font-medium">
                  {isCritical ? (
                    <AlertCircle className="w-3.5 h-3.5 text-[#b84d47] flex-shrink-0" />
                  ) : isWarning ? (
                    <AlertTriangle className="w-3.5 h-3.5 text-[#c98a2c] flex-shrink-0" />
                  ) : (
                    <Info className="w-3.5 h-3.5 text-[#5c7080] flex-shrink-0" />
                  )}
                  <span className="text-xs font-semibold">{sig.type.replace(/_/g, ' ')}</span>
                </div>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    isCritical
                      ? 'bg-[#b84d47]/20 text-[#b84d47]'
                      : isWarning
                      ? 'bg-[#c98a2c]/20 text-[#c98a2c]'
                      : 'bg-[#5c7080]/20 text-[#a09f99]'
                  }`}
                >
                  {sig.severity}
                </span>
              </div>

              <p className="text-xs text-[#d1d0c9] leading-relaxed pl-5">{sig.explanation}</p>

              <div className="flex items-center justify-between text-[11px] text-[#a09f99] pt-1 pl-5 border-t border-white/5">
                <span>
                  Confidence: <span className="font-medium text-[#f4f3ef]">{sig.confidence}</span>
                </span>
                <span>
                  Requires Review:{' '}
                  <span className="font-semibold text-[#f4f3ef]">
                    {sig.requires_review ? 'Yes' : 'No'}
                  </span>
                </span>
              </div>

              {sig.advisory_note && (
                <div className="text-[10px] text-[#a09f99]/80 pl-5 italic">
                  Note: {sig.advisory_note}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
