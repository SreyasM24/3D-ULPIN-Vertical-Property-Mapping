import { apiClient } from './client.ts';
import {
  DigitalTwinValidationReport,
  ValidationRuleDefinition,
  ValidationHistoryItem,
  ValidationRuleResult,
  ApiResponse,
} from '../../types/api.ts';

let cachedRuleDefs: ValidationRuleDefinition[] | null = null;

export async function getRuleDefinitions(): Promise<ValidationRuleDefinition[]> {
  if (cachedRuleDefs && cachedRuleDefs.length > 0) return cachedRuleDefs;
  try {
    const res = await apiClient<ValidationRuleDefinition[]>('/validation/rules');
    cachedRuleDefs = res.data || [];
    return cachedRuleDefs;
  } catch {
    return [];
  }
}

export function normalizeValidationReport(
  raw: any,
  ruleDefs?: ValidationRuleDefinition[]
): DigitalTwinValidationReport {
  if (!raw) return raw;

  const issueMap = new Map<string, any>();
  (raw.issues || []).forEach((issue: any) => {
    issueMap.set(issue.rule_id, issue);
  });

  const evaluated_rules: ValidationRuleResult[] = [];
  if (ruleDefs && ruleDefs.length > 0) {
    ruleDefs.forEach((def) => {
      const issue = issueMap.get(def.rule_id);
      if (issue) {
        evaluated_rules.push({
          rule_id: def.rule_id,
          rule_name: def.title || def.rule_id,
          category: def.category || 'GENERAL',
          status:
            issue.severity === 'CRITICAL' || issue.severity === 'ERROR'
              ? 'ERROR'
              : 'WARNING',
          message: issue.explanation || def.description,
          details: issue.suggested_remediation,
        });
      } else {
        evaluated_rules.push({
          rule_id: def.rule_id,
          rule_name: def.title || def.rule_id,
          category: def.category || 'GENERAL',
          status: 'PASSED',
          message: `${def.title} satisfied and compliant.`,
          details: def.description,
        });
      }
    });
  } else {
    (raw.issues || []).forEach((issue: any) => {
      evaluated_rules.push({
        rule_id: issue.rule_id,
        rule_name: `${issue.rule_id}: ${issue.explanation?.substring(0, 45) || issue.rule_id}`,
        category: issue.category || 'GENERAL',
        status:
          issue.severity === 'CRITICAL' || issue.severity === 'ERROR'
            ? 'ERROR'
            : issue.severity === 'WARNING'
            ? 'WARNING'
            : 'PASSED',
        message: issue.explanation,
        details: issue.suggested_remediation,
      });
    });
  }

  const qualityScore = raw.quality_score || { total_score: 0, grade: 'INVALID_OR_INCOMPLETE' };

  return {
    ...raw,
    critical_errors: raw.critical_errors_count ?? 0,
    warnings: raw.warnings_count ?? 0,
    quality_grade: qualityScore.grade || 'INVALID_OR_INCOMPLETE',
    disclaimer: qualityScore.disclaimer || 'Cadastral technical data-quality indicator.',
    evaluated_rules: raw.evaluated_rules || evaluated_rules,
    clash_findings: (raw.clash_findings || []).map((clash: any) => ({
      ...clash,
      id: clash.id || `${clash.entity_a_identifier}-${clash.entity_b_identifier}`,
      type: clash.type || clash.classification || 'VOLUMETRIC_INTERSECTION',
      severity: clash.severity || clash.classification || 'WARNING',
      description: clash.description || clash.explanation,
      unit_a_ulpin: clash.unit_a_ulpin || clash.entity_a_identifier,
      unit_b_ulpin: clash.unit_b_ulpin || clash.entity_b_identifier,
      overlap_volume_cum: clash.overlap_volume_cum ?? clash.estimated_overlap_volume_cu_m,
      z_range: clash.z_range || (clash.overlap_elevation_range ? {
        z_min: clash.overlap_elevation_range[0],
        z_max: clash.overlap_elevation_range[1],
      } : undefined),
    })),
  };
}

export async function validateParcel(
  parcelId: string,
  persist: boolean = true
): Promise<DigitalTwinValidationReport> {
  const [res, ruleDefs] = await Promise.all([
    apiClient<DigitalTwinValidationReport>(
      `/validation/parcel/${parcelId}?persist=${persist}`,
      { method: 'POST' }
    ),
    getRuleDefinitions(),
  ]);
  return normalizeValidationReport(res.data, ruleDefs);
}

export async function getValidationReportByRunId(
  validationRunId: string
): Promise<DigitalTwinValidationReport> {
  const [res, ruleDefs] = await Promise.all([
    apiClient<DigitalTwinValidationReport>(`/validation/report/${validationRunId}`),
    getRuleDefinitions(),
  ]);
  return normalizeValidationReport(res.data, ruleDefs);
}

export async function getValidationHistory(
  entityId: string,
  limit: number = 20
): Promise<ValidationHistoryItem[]> {
  const res = await apiClient<ValidationHistoryItem[]>(
    `/validation/history/${entityId}?limit=${limit}`
  );
  return res.data;
}

export async function listValidationRules(): Promise<ValidationRuleDefinition[]> {
  return getRuleDefinitions();
}

export const validationApi = {
  getValidationReport: async (
    parcelId: string
  ): Promise<ApiResponse<DigitalTwinValidationReport>> => {
    const data = await validateParcel(parcelId);
    return { success: true, data };
  },
  validateParcel: async (
    parcelId: string,
    persist: boolean = true
  ): Promise<ApiResponse<DigitalTwinValidationReport>> => {
    const data = await validateParcel(parcelId, persist);
    return { success: true, data };
  },
  runValidation: async (
    parcelId: string
  ): Promise<ApiResponse<DigitalTwinValidationReport>> => {
    const data = await validateParcel(parcelId);
    return { success: true, data };
  },
  getValidationReportByRunId: async (
    runId: string
  ): Promise<ApiResponse<DigitalTwinValidationReport>> => {
    const data = await getValidationReportByRunId(runId);
    return { success: true, data };
  },
  getValidationHistory: async (
    entityId: string,
    limit?: number
  ): Promise<ApiResponse<ValidationHistoryItem[]>> => {
    const data = await getValidationHistory(entityId, limit);
    return { success: true, data };
  },
  listRules: async (): Promise<ApiResponse<ValidationRuleDefinition[]>> => {
    const data = await listValidationRules();
    return { success: true, data };
  },
};
