import React, { useState } from 'react';
import { ClashFinding, ValidationRuleResult } from '../../types/api.ts';
import {
  AlertTriangle,
  XCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Box,
  Layers,
  Search,
} from 'lucide-react';

interface ValidationIssuesProps {
  clashFindings: ClashFinding[];
  rules: ValidationRuleResult[];
}

export const ValidationIssues: React.FC<ValidationIssuesProps> = ({
  clashFindings,
  rules,
}) => {
  const [filter, setFilter] = useState<'ALL' | 'ERROR' | 'WARNING' | 'PASSED'>('ALL');
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');

  const filteredRules = rules.filter((rule) => {
    if (filter !== 'ALL' && rule.status !== filter) return false;
    if (categoryFilter !== 'ALL' && rule.category !== categoryFilter) return false;
    return true;
  });

  const categories = Array.from(new Set(rules.map((r) => r.category)));

  const errorCount = rules.filter((r) => r.status === 'ERROR').length;
  const warningCount = rules.filter((r) => r.status === 'WARNING').length;
  const passedCount = rules.filter((r) => r.status === 'PASSED').length;

  return (
    <div className="space-y-6">
      {/* 1. Volumetric Clash Findings (if any) */}
      {clashFindings.length > 0 && (
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-[#2d3034]">
            <div className="flex items-center gap-2">
              <Box className="w-4 h-4 text-[#d97757]" />
              <h3 className="text-sm font-semibold text-[#f4f3ef]">
                Spatial Clash Findings ({clashFindings.length})
              </h3>
            </div>
            <span className="text-[11px] text-[#a09f99]">Volumetric Intersection Detection</span>
          </div>

          <div className="space-y-2">
            {clashFindings.map((clash) => (
              <div
                key={clash.id}
                className="p-3 rounded bg-[#222428] border border-[#2d3034] text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-[#f4f3ef] flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-[#c98a2c]" />
                    {(clash.type || 'VOLUMETRIC_INTERSECTION').replace(/_/g, ' ')}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-[#c98a2c]/15 text-[#d49438] border border-[#c98a2c]/30">
                    {clash.severity}
                  </span>
                </div>

                <p className="text-[#a09f99] pl-5">{clash.description}</p>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[#a09f99] pl-5 pt-1">
                  {clash.unit_a_ulpin && (
                    <span>
                      Target ULPIN: <span className="font-mono text-[#f4f3ef]">{clash.unit_a_ulpin}</span>
                    </span>
                  )}
                  {clash.overlap_volume_cum !== undefined && (
                    <span>
                      Overlap Volume: <span className="font-mono text-[#d97757]">{clash.overlap_volume_cum} cu.m</span>
                    </span>
                  )}
                  {clash.z_range && (
                    <span>
                      Elevation: <span className="font-mono text-[#f4f3ef]">{clash.z_range.z_min}m to {clash.z_range.z_max}m</span>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. Deterministic Validation Rules Hierarchy */}
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#2d3034]">
          <div>
            <h3 className="text-sm font-semibold text-[#f4f3ef]">
              Deterministic Cadastral Rule Evaluations
            </h3>
            <p className="text-xs text-[#a09f99] mt-0.5">
              {rules.length > 0 ? `${rules.length} rigorous geometric and attribution invariants evaluated against source data.` : 'Rigorous geometric and attribution invariants evaluated against source data.'}
            </p>
          </div>

          {/* Status Filter Tabs */}
          <div className="flex items-center gap-1 bg-[#222428] p-1 rounded border border-[#2d3034] text-xs">
            <button
              onClick={() => setFilter('ALL')}
              className={`px-2.5 py-1 rounded transition-colors font-medium ${
                filter === 'ALL'
                  ? 'bg-[#2d3034] text-[#f4f3ef]'
                  : 'text-[#a09f99] hover:text-[#f4f3ef]'
              }`}
            >
              All ({rules.length})
            </button>
            <button
              onClick={() => setFilter('ERROR')}
              className={`px-2.5 py-1 rounded transition-colors font-medium flex items-center gap-1 ${
                filter === 'ERROR'
                  ? 'bg-[#b84d47]/20 text-[#c45852]'
                  : 'text-[#a09f99] hover:text-[#c45852]'
              }`}
            >
              Errors ({errorCount})
            </button>
            <button
              onClick={() => setFilter('WARNING')}
              className={`px-2.5 py-1 rounded transition-colors font-medium flex items-center gap-1 ${
                filter === 'WARNING'
                  ? 'bg-[#c98a2c]/20 text-[#d49438]'
                  : 'text-[#a09f99] hover:text-[#d49438]'
              }`}
            >
              Warnings ({warningCount})
            </button>
            <button
              onClick={() => setFilter('PASSED')}
              className={`px-2.5 py-1 rounded transition-colors font-medium flex items-center gap-1 ${
                filter === 'PASSED'
                  ? 'bg-[#4e8a5b]/20 text-[#5a9e69]'
                  : 'text-[#a09f99] hover:text-[#5a9e69]'
              }`}
            >
              Passed ({passedCount})
            </button>
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
          <span className="text-[#a09f99] text-[11px] whitespace-nowrap">Category:</span>
          <button
            onClick={() => setCategoryFilter('ALL')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium whitespace-nowrap transition-colors ${
              categoryFilter === 'ALL'
                ? 'bg-[#c86446]/20 text-[#d97757] border border-[#c86446]/40'
                : 'bg-[#222428] text-[#a09f99] hover:text-[#f4f3ef] border border-transparent'
            }`}
          >
            All Categories
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium whitespace-nowrap transition-colors ${
                categoryFilter === cat
                  ? 'bg-[#c86446]/20 text-[#d97757] border border-[#c86446]/40'
                  : 'bg-[#222428] text-[#a09f99] hover:text-[#f4f3ef] border border-transparent'
              }`}
            >
              {cat.replace(/_/g, ' ')}
            </button>
          ))}
        </div>

        {/* Expandable Rules List */}
        <div className="space-y-2">
          {filteredRules.map((rule) => {
            const isExpanded = expandedRuleId === rule.rule_id;
            return (
              <div
                key={rule.rule_id}
                className="bg-[#222428] border border-[#2d3034] rounded-lg overflow-hidden transition-all text-xs"
              >
                <div
                  onClick={() => setExpandedRuleId(isExpanded ? null : rule.rule_id)}
                  className="p-3 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#282a30] transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {rule.status === 'PASSED' ? (
                      <CheckCircle2 className="w-4 h-4 text-[#4e8a5b] flex-shrink-0" />
                    ) : rule.status === 'WARNING' ? (
                      <AlertTriangle className="w-4 h-4 text-[#c98a2c] flex-shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-[#b84d47] flex-shrink-0" />
                    )}
                    <span className="font-mono text-[#a09f99] text-[11px] flex-shrink-0">
                      [{rule.rule_id}]
                    </span>
                    <span className="font-medium text-[#f4f3ef] truncate">
                      {rule.rule_name}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span className="text-[10px] uppercase text-[#a09f99] bg-[#18191b] px-2 py-0.5 rounded border border-[#2d3034]">
                      {rule.category.replace(/_/g, ' ')}
                    </span>
                    {isExpanded ? (
                      <ChevronUp className="w-3.5 h-3.5 text-[#a09f99]" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-[#a09f99]" />
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="p-3.5 bg-[#18191b] border-t border-[#2d3034] text-[#a09f99] space-y-2">
                    <div>
                      <span className="text-[10px] uppercase text-[#a09f99] font-medium block">
                        Engine Evaluation Output:
                      </span>
                      <p className="text-xs text-[#f4f3ef] mt-0.5">{rule.message}</p>
                    </div>

                    {rule.details && (
                      <div className="p-2.5 rounded bg-[#222428] border border-[#2d3034] text-[11px] font-mono text-[#d1d0c9]">
                        {rule.details}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {filteredRules.length === 0 && (
            <div className="p-6 text-center text-[#a09f99] text-xs">
              No rules matching current filter criteria.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
