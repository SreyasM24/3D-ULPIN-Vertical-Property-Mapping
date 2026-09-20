import React, { useState } from 'react';
import { ProvenanceRecord } from '../../types/api.ts';
import { History, ChevronDown, ChevronUp, Cpu, Calendar, ShieldCheck } from 'lucide-react';

interface ProvenancePanelProps {
  provenance: ProvenanceRecord;
  defaultExpanded?: boolean;
}

export const ProvenancePanel: React.FC<ProvenancePanelProps> = ({
  provenance,
  defaultExpanded = true,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-[#222428] border border-[#2d3034] rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 bg-[#26282d] hover:bg-[#2b2d32] transition-colors text-left font-medium text-[#f4f3ef]"
      >
        <div className="flex items-center gap-2">
          <History className="w-3.5 h-3.5 text-[#d97757]" />
          <span>Cadastral Lineage & Sensor Provenance</span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-3.5 h-3.5 text-[#a09f99]" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-[#a09f99]" />
        )}
      </button>

      {isExpanded && (
        <div className="p-3 space-y-2 text-[#a09f99] border-t border-[#2d3034]">
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Acquisition Source:</span>
            <span className="font-mono text-[#f4f3ef] font-medium text-[11px] truncate max-w-[180px]">
              {provenance.source}
            </span>
          </div>

          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Processing Method:</span>
            <span className="text-[#f4f3ef] font-medium text-[11px] truncate max-w-[180px]">
              {provenance.method}
            </span>
          </div>

          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Cadastral Engine Model:</span>
            <span className="font-mono text-[#6b8e72] font-medium text-[11px]">
              {provenance.model} ({provenance.model_version})
            </span>
          </div>

          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Data Lifecycle Stage:</span>
            <span className="font-mono text-[#f4f3ef] text-[11px]">{provenance.data_stage}</span>
          </div>

          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Spatial Uncertainty:</span>
            <span className="font-mono text-[#d97757] font-medium text-[11px]">
              {provenance.uncertainty_m !== undefined ? `±${provenance.uncertainty_m.toFixed(2)} m` : 'N/A'}
            </span>
          </div>

          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Timestamp:</span>
            <span className="font-mono text-[#a09f99] text-[11px]">
              {new Date(provenance.timestamp).toLocaleString()}
            </span>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-[#2d3034]">
            <span className="text-[10px] uppercase font-medium">Verified By:</span>
            <span className="text-[#f4f3ef] text-[11px]">{provenance.operator_or_system}</span>
          </div>
        </div>
      )}
    </div>
  );
};
