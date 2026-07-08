// 后端 REST 封装（与现有 FastAPI /api、/l5 完全对齐，无需改动后端）
import type { Flow } from './converters'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function req<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    headers: JSON_HEADERS,
    ...opts,
  })
  if (!r.ok) {
    const text = await r.text().catch(() => '')
    throw new Error(`${r.status} ${r.statusText} ${text}`)
  }
  return r.json() as Promise<T>
}

export interface WorkflowSummary {
  id: string
  name: string
  description?: string
  updated_at?: string
}

export interface WorkflowDetail {
  id: string
  name: string
  flow: Flow
}

export interface NodeLog {
  node_id: string
  node_type: string
  status: string
  error?: string
  duration?: number
}

export interface ExecuteResult {
  run_id: string
  mode: string
  execution: {
    success: boolean
    node_logs: NodeLog[]
    [k: string]: any
  }
}

export const api = {
  listWorkflows: () => req<WorkflowSummary[]>('/api/workflows'),

  getWorkflow: async (id: string): Promise<WorkflowDetail> => {
    const wf = await req<{ id: string; name: string; flow_json?: string; [k: string]: any }>(
      `/api/workflows/${id}`,
    )
    const flow: Flow =
      typeof wf.flow_json === 'string'
        ? JSON.parse(wf.flow_json)
        : wf.flow_json || { nodes: [], edges: [] }
    return { id: wf.id, name: wf.name, flow }
  },

  createWorkflow: (name: string, flow: Flow) =>
    req<{ id: string; success: boolean }>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify({ name, flow }),
    }),

  updateWorkflow: (id: string, flow: Flow) =>
    req<{ success: boolean }>(`/api/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ flow }),
    }),

  compileToFlow: (query: string) => req<Flow>('/api/compile-to-flow', {
    method: 'POST',
    body: JSON.stringify({ query }),
  }),

  palette: () => req<any[]>('/api/palette'),

  execute: (id: string, mode: 'dry_run' | 'real' = 'dry_run') =>
    req<ExecuteResult>(`/api/workflows/${id}/execute?mode=${mode}`, {
      method: 'POST',
    }),
}
