export interface ParametricStats {
  total_cohorts: number;
  total_workers: number;
  total_active_policies: number;
  total_disbursed_inr: number;
  pending_approvals: number;
}

export const EMPTY_PARAMETRIC_STATS: ParametricStats = {
  total_cohorts: 0,
  total_workers: 0,
  total_active_policies: 0,
  total_disbursed_inr: 0,
  pending_approvals: 0,
};

export async function readApiJson<T>(response: Response, fallback: T): Promise<T> {
  const body = await response.json().catch(() => null);
  return response.ok ? (body as T) : fallback;
}

export function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value : [];
}

export function asParametricStats(value: unknown): ParametricStats {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return EMPTY_PARAMETRIC_STATS;
  }

  const stats = value as Partial<ParametricStats>;
  return {
    total_cohorts: typeof stats.total_cohorts === "number" ? stats.total_cohorts : 0,
    total_workers: typeof stats.total_workers === "number" ? stats.total_workers : 0,
    total_active_policies:
      typeof stats.total_active_policies === "number" ? stats.total_active_policies : 0,
    total_disbursed_inr:
      typeof stats.total_disbursed_inr === "number" ? stats.total_disbursed_inr : 0,
    pending_approvals: typeof stats.pending_approvals === "number" ? stats.pending_approvals : 0,
  };
}
