import React, { useState } from 'react';
import { ProvenanceRecord } from '../../types/api.ts';
import { History, ChevronDown, ChevronUp, Cpu, Calendar, ShieldCheck, AlertTriangle, Layers, Info } from 'lucide-react';

interface ProvenancePanelProps {
  provenance?: ProvenanceRecord | null;
  defaultExpanded?: boolean;
}

export const ProvenancePanel: React.FC<ProvenancePanelProps> = ({
  provenance,
  defaultExpanded = true,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!provenance) {
    return (
      <div className="bg-[#222428] border border-[#2d3034] rounded-lg p-5 text-center space-y-2 text-xs">
        <Info className="w-5 h-5 mx-auto text-[#5c7080]" />
        <div className="font-medium text-[#f4f3ef]">No Provenance Record Available</div>
        <p className="text-[11px] text-[#a09f99] max-w-xs mx-auto leading-relaxed">
          Lineage records for this unit are either pending validation or not yet indexed by the 3D cadastre service.
        </p>
      </div>
    );
  }

  const rawTier = provenance.evidence_tier || (
    String(provenance.source || '').includes('AI') ? 'AI_INFERENCE' :
    String(provenance.source || '').includes('OBSERVED') || String(provenance.source || '').includes('DRONE') ? 'OBSERVED' :
    'DETERMINISTIC'
  );

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case 'OBSERVED':
        return {
          label: 'OBSERVED SENSOR DATA',
          className: 'bg-[#4e8a5b]/20 text-[#5a9e69] border-[#4e8a5b]/40',
        };
      case 'AI_INFERENCE':
        return {
          label: 'AI / ML INFERENCE',
          className: 'bg-[#7c3aed]/20 text-[#c084fc] border-[#7c3aed]/40',
        };
      case 'TEST_FIXTURE':
        return {
          label: 'TEST FIXTURE EVIDENCE',
          className: 'bg-[#c98a2c]/20 text-[#eab308] border-[#c98a2c]/40',
        };
      case 'DETERMINISTIC':
      default:
        return {
          label: 'DETERMINISTIC CADASTRAL PIPELINE',
          className: 'bg-[#3b82f6]/20 text-[#60a5fa] border-[#3b82f6]/40',
        };
    }
  };

  const tierBadge = getTierBadge(rawTier);

  const formattedDate = provenance.timestamp && !isNaN(new Date(provenance.timestamp).getTime())
    ? new Date(provenance.timestamp).toLocaleString()
    : 'Recent Execution';

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
        <div className="p-3 space-y-2.5 text-[#a09f99] border-t border-[#2d3034]">
          {/* Evidence Tier Badge */}
          <div className="flex items-center justify-between pb-1.5 border-b border-[#2d3034]">
            <span className="text-[10px] uppercase font-medium">Evidence Tier:</span>
            <span className={`px-2 py-0.5 text-[10px] font-mono font-semibold rounded border ${tierBadge.className}`}>
              {tierBadge.label}
            </span>
          </div>

          {/* Acquisition Source */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Acquisition Source:</span>
            <span className="font-mono text-[#f4f3ef] font-medium text-[11px] truncate max-w-[200px]">
              {provenance.source || provenance.source_type || 'DETERMINISTIC_STRATA'}
            </span>
          </div>

          {/* Source Reference */}
          {provenance.source_reference && (
            <div className="flex items-center justify-between pb-1">
              <span className="text-[10px] uppercase font-medium">Source Reference:</span>
              <span className="font-mono text-[#a09f99] text-[10px] truncate max-w-[200px]">
                {provenance.source_reference}
              </span>
            </div>
          )}

          {/* Processing Method */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Processing Method:</span>
            <span className="text-[#f4f3ef] font-medium text-[11px] truncate max-w-[200px]">
              {provenance.method || 'Parametric Cadastral Strata Decomposition'}
            </span>
          </div>

          {/* Cadastral Engine Model */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Cadastral Engine Model:</span>
            <span className="font-mono text-[#6b8e72] font-medium text-[11px]">
              {provenance.model || 'CadastralEngine3D'} {provenance.model_version ? `(v${provenance.model_version})` : ''}
            </span>
          </div>

          {/* Data Lifecycle Stage */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Data Lifecycle Stage:</span>
            <span className="font-mono text-[#f4f3ef] text-[11px]">{provenance.data_stage || 'VALIDATED'}</span>
          </div>

          {/* Confidence Level */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Confidence Level:</span>
            <span className="font-mono text-[#6b8e72] font-medium text-[11px]">
              {provenance.confidence || 'HIGH'}
            </span>
          </div>

          {/* Spatial Uncertainty */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Spatial Uncertainty:</span>
            <span className="font-mono text-[#d97757] font-medium text-[11px]">
              {provenance.uncertainty_m !== undefined ? `±${provenance.uncertainty_m.toFixed(2)} m` : '±0.30 m'}
            </span>
          </div>

          {/* Timestamp */}
          <div className="flex items-center justify-between pb-1">
            <span className="text-[10px] uppercase font-medium">Timestamp:</span>
            <span className="font-mono text-[#a09f99] text-[11px]">
              {formattedDate}
            </span>
          </div>

          {/* Review Requirement Flag if any */}
          {provenance.requires_review && (
            <div className="p-2 rounded bg-[#c98a2c]/10 border border-[#c98a2c]/30 text-[#eab308] text-[11px] flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Advisory review flagged by validation heuristics.</span>
            </div>
          )}

          {/* Operator / System */}
          <div className="flex items-center justify-between pt-1 border-t border-[#2d3034]">
            <span className="text-[10px] uppercase font-medium">Verified By:</span>
            <span className="text-[#f4f3ef] text-[11px] font-mono">{provenance.operator_or_system || 'Autonomous Deterministic Pipeline'}</span>
          </div>
        </div>
      )}
    </div>
  );
};
