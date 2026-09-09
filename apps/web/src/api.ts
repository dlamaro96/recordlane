// SPDX-License-Identifier: Apache-2.0
export type ApiState = {
  overview: any;
  domains: any[];
  sources: any[];
  records: any[];
  entities: any[];
  tasks: any[];
  configs: any[];
  simulations: any[];
  relationships: any[];
  operations: any;
  audit: any[];
  me: any;
};

const base = import.meta.env.VITE_API_URL || '/api/v1';

export async function request(path: string, role = 'administrator', init?: RequestInit) {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Recordlane-Role': role,
      'X-Recordlane-User': role === 'approver' ? 'maya.approver' : `demo.${role}`,
      'X-Recordlane-Workspace': 'demo',
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload?.detail?.message || payload?.detail?.code || `Request failed (${response.status})`);
    (error as any).status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export async function loadState(role: string): Promise<ApiState> {
  const paths = ['/overview', '/domains', '/sources', '/source-records', '/entities', '/review-tasks', '/configurations', '/simulations', '/relationships', '/operations', '/me'];
  const values = await Promise.all(paths.map((p) => request(p, role)));
  let audit: any[] = [];
  try { audit = await request('/audit', role); } catch { /* role-aware absence is intentional */ }
  return {
    overview: values[0], domains: values[1], sources: values[2], records: values[3],
    entities: values[4], tasks: values[5], configs: values[6], simulations: values[7],
    relationships: values[8], operations: values[9], me: values[10], audit,
  };
}
