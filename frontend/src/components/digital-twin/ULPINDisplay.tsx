import React, { useState } from 'react';
import { Copy, Check, Info } from 'lucide-react';

interface ULPINDisplayProps {
  ulpin3d: string;
  baseUlpin?: string;
  levelCode?: string;
  unitNumber?: string;
  checksum?: string;
  classification?: string;
  compact?: boolean;
}

export const ULPINDisplay: React.FC<ULPINDisplayProps> = ({
  ulpin3d,
  baseUlpin,
  levelCode,
  unitNumber,
  checksum,
  classification,
  compact = false,
}) => {
  const [copied, setCopied] = useState(false);

  // Parse 3D ULPIN if parts not explicitly supplied
  // Format: <BaseParcelULPIN>-<LevelCode>-<UnitCode>-<Checksum>
  const parts = ulpin3d.split('-');
  const computedBase = baseUlpin || parts[0] || '—';
  const computedLevel = levelCode || parts[1] || '—';
  const computedUnit = unitNumber || parts[2] || '—';
  const computedChecksum = checksum || parts[3] || '—';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(ulpin3d);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between gap-2 p-2 bg-[#222428] rounded border border-[#34373d]">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">3D ULPIN</span>
          <span className="font-mono text-xs font-semibold text-[#f4f3ef] tracking-wide truncate">
            {ulpin3d}
          </span>
        </div>
        <button
          onClick={handleCopy}
          className="p-1 hover:bg-[#2b2d32] text-[#a09f99] hover:text-[#f4f3ef] rounded transition-colors"
          title="Copy 3D ULPIN"
          aria-label="Copy 3D ULPIN"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-[#4e8a5b]" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
    );
  }

  return (
    <div className="bg-[#222428] border border-[#34373d] rounded-lg p-4 space-y-3">
      {/* Header and Prototype Label */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-wider text-[#a09f99] uppercase">
          Vertical Property Identifier
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium bg-[#c86446]/15 text-[#d97757] border border-[#c86446]/30 rounded">
          <Info className="w-3 h-3" />
          Prototype 3D ULPIN
        </span>
      </div>

      {/* Primary 3D ULPIN Display with Copy Action */}
      <div className="relative group bg-[#18191b] p-3 rounded border border-[#2d3034] flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium tracking-wider mb-0.5">
            Full 3D ULPIN String
          </div>
          <div className="font-mono text-sm sm:text-base font-semibold tracking-wider text-[#f4f3ef] break-all">
            {ulpin3d}
          </div>
        </div>
        <button
          onClick={handleCopy}
          className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded bg-[#2b2d32] hover:bg-[#34373d] text-[#f4f3ef] border border-[#3e4249] transition-colors"
          title="Copy full 3D ULPIN"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-[#4e8a5b]" />
              <span className="text-[#4e8a5b]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-[#a09f99]" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Component Breakdown: Base Parcel, Level, Unit, Checksum */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
        <div className="bg-[#1c1d20] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">Base Parcel</div>
          <div className="font-mono text-xs font-medium text-[#f4f3ef] truncate mt-0.5" title={computedBase}>
            {computedBase}
          </div>
        </div>

        <div className="bg-[#1c1d20] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">Level / Floor</div>
          <div className="font-mono text-xs font-medium text-[#6b8e72] mt-0.5">
            {computedLevel}
          </div>
        </div>

        <div className="bg-[#1c1d20] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">Vertical Unit</div>
          <div className="font-mono text-xs font-medium text-[#d97757] mt-0.5">
            {computedUnit}
          </div>
        </div>

        <div className="bg-[#1c1d20] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">Checksum</div>
          <div className="font-mono text-xs font-medium text-[#5c7080] mt-0.5">
            {computedChecksum}
          </div>
        </div>
      </div>

      {classification && (
        <div className="text-xs text-[#a09f99] flex items-center justify-between border-t border-[#2d3034] pt-2">
          <span>Cadastral Classification:</span>
          <span className="font-medium text-[#f4f3ef]">{classification}</span>
        </div>
      )}

      <div className="text-[11px] text-[#a09f99]/80 italic">
        * Prototype 3D ULPIN formatted for SIH 26011 vertical stratification; not a gazetted legal title.
      </div>
    </div>
  );
};
