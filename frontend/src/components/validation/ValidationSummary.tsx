import React from 'react';
import { DigitalTwinValidationReport } from '../../types/api.ts';
import { ShieldCheck, AlertTriangle, XCircle, Info, RefreshCw } from 'lucide-react';

interface ValidationSummaryProps {
  report: DigitalTwinValidationReport;
  onRerunValidation?: () => void;
  isRerunning?: boolean;
}

export const ValidationSummary: React.FC<ValidationSummaryProps> = ({
  report,
  onRerunValidation,
  isRerunning = false,
}) => {
  const getGradeBadge = (grade: string) => {
    switch (grade) {
      case 'HIGH_CONFIDENCE':
        return {
          bg: 'bg-[#4e8a5b]/15 text-[#5a9e69] border-[#4e8a5b]/30',
          label: 'HIGH CONFIDENCE',
        };
      case 'GOOD_QUALITY':
        return {
          bg: 'bg-[#6b8e72]/15 text-[#7c9d83] border-[#6b8e72]/30',
          label: 'GOOD QUALITY',
        };
      case 'REQUIRES_REVIEW':
        return {
          bg: 'bg-[#c98a2c]/15 text-[#d49438] border-[#c98a2c]/30',
          label: 'REQUIRES REVIEW',
        };
      default:
        return {
          bg: 'bg-[#b84d47]/15 text-[#c45852] border-[#b84d47]/30',
          label: 'INVALID OR INCOMPLETE',
        };
    }
  };

  const scoreNum = typeof report.quality_score === 'number' ? report.quality_score : report.quality_score?.total_score ?? 0;
  const gradeStr = report.quality_grade || (typeof report.quality_score === 'object' ? report.quality_score?.grade : '') || 'INVALID_OR_INCOMPLETE';
  const gradeInfo = getGradeBadge(gradeStr);
  const criticalCount = report.critical_errors ?? report.critical_errors_count ?? 0;
  const warningsCount = report.warnings ?? report.warnings_count ?? 0;
  const clashCount = report.clash_findings?.length ?? 0;
  const totalRules = report.total_rules_executed ?? report.evaluated_rules?.length ?? 0;

  return (
    <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-4">
      {/* Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#2d3034]">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">
            Deterministic Quality Assessment
          </div>
          <h2 className="text-base font-semibold text-[#f4f3ef] mt-0.5">
            Cadastral Topology & Volumetric Validation
          </h2>
        </div>

        {onRerunValidation && (
          <button
            onClick={onRerunValidation}
            disabled={isRerunning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-[#222428] hover:bg-[#2b2d32] border border-[#34373d] text-[#f4f3ef] transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRerunning ? 'animate-spin text-[#d97757]' : 'text-[#a09f99]'}`} />
            <span>{isRerunning ? 'Running Engine…' : (totalRules > 0 ? `Re-run ${totalRules} Rules` : 'Re-run Validation')}</span>
          </button>
        )}
      </div>

      {/* Mandatory Statutory Disclaimer Banner */}
      <div className="flex items-start gap-2.5 p-3 rounded bg-[#222428] border border-[#2d3034] text-xs text-[#d1d0c9]">
        <Info className="w-4 h-4 text-[#d97757] flex-shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold text-[#f4f3ef]">Cadastral Notice: </span>
          {report.disclaimer || (typeof report.quality_score === 'object' && report.quality_score?.disclaimer) || 'This is a technical data-quality assessment, not legal title confirmation.'}
        </div>
      </div>

      {/* Key Quality Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Quality Score */}
        <div className="bg-[#222428] p-3 rounded-lg border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Quality Score</div>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-2xl font-bold font-mono text-[#f4f3ef]">
              {scoreNum.toFixed(1)}
            </span>
            <span className="text-xs text-[#a09f99]">/ 100</span>
          </div>
        </div>

        {/* Quality Grade */}
        <div className="bg-[#222428] p-3 rounded-lg border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Technical Grade</div>
          <div className="mt-1.5">
            <span
              className={`inline-block px-2 py-0.5 text-xs font-semibold rounded border ${gradeInfo.bg}`}
            >
              {gradeInfo.label}
            </span>
          </div>
        </div>

        {/* Critical Errors */}
        <div className="bg-[#222428] p-3 rounded-lg border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Critical Errors</div>
          <div className="flex items-center gap-1.5 mt-1">
            {criticalCount > 0 ? (
              <XCircle className="w-4 h-4 text-[#b84d47]" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-[#4e8a5b]" />
            )}
            <span className={`text-xl font-bold font-mono ${criticalCount > 0 ? 'text-[#b84d47]' : 'text-[#f4f3ef]'}`}>
              {criticalCount}
            </span>
          </div>
        </div>

        {/* Warnings & Clashes */}
        <div className="bg-[#222428] p-3 rounded-lg border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Warnings & Clashes</div>
          <div className="flex items-center gap-1.5 mt-1">
            {warningsCount > 0 ? (
              <AlertTriangle className="w-4 h-4 text-[#c98a2c]" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-[#4e8a5b]" />
            )}
            <span className="text-xl font-bold font-mono text-[#f4f3ef]">
              {warningsCount}
            </span>
            <span className="text-xs text-[#a09f99]">
              ({clashCount} clashes)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
