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
  quality: any;
  operations: any;
  audit: any[];
  serviceAccounts: any[];
  secrets: any[];
  me: any;
};

const base = import.meta.env.VITE_API_URL || '/api/v1';

export async function request(path: string, role = 'administrator', init?: RequestInit) {
  const response = await fetch(`${base}${path}`, {
    ...init,
    credentials: 'same-origin',
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
    if (response.status === 401 && typeof window !== 'undefined' && !import.meta.env.DEV) {
      const returnTo = `${window.location.pathname}${window.location.hash}`;
      window.location.assign(`/auth/login?return_to=${encodeURIComponent(returnTo)}`);
    }
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export async function loadState(role: string): Promise<ApiState> {
  const paths = ['/overview', '/domains', '/sources', '/source-records', '/entities', '/review-tasks', '/configurations', '/simulations', '/relationships', '/quality/profile?domain=supplier', '/operations', '/me'];
  const values = await Promise.all(paths.map((p) => request(p, role)));
  const optional = await Promise.allSettled([
    request('/audit', role), request('/service-accounts', role), request('/secrets', role),
  ]);
  const readOptional = (index: number) => optional[index].status === 'fulfilled' ? (optional[index] as PromiseFulfilledResult<any[]>).value : [];
  return {
    overview: values[0], domains: values[1], sources: values[2], records: values[3],
    entities: values[4], tasks: values[5], configs: values[6], simulations: values[7],
    relationships: values[8], quality: values[9], operations: values[10], me: values[11],
    audit: readOptional(0), serviceAccounts: readOptional(1), secrets: readOptional(2),
  };
}
