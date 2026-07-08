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

// ---- 调度 (F012.2) ----
export interface SchedulerTrigger {
  id: string
  name: string
  cron?: string
  interval_seconds?: number
  target_workflow: string
  enabled: boolean
  next_run?: string
  last_run?: string
  created_at?: string
}

export interface SchedulerStatus {
  running: boolean
  trigger_count: number
  enabled_count: number
}

// ---- 执行日志 (F012.3) ----
export interface ExecutionDetail {
  run_id: string
  workflow_id: string
  mode: string
  status: string
  success: boolean
  started_at?: string
  finished_at?: string
  duration?: number
  node_logs: NodeLogDetail[]
}

export interface NodeLogDetail {
  node_id: string
  node_type: string
  status: string
  error?: string
  duration?: number
  started_at?: string
  finished_at?: string
  screenshot_b64?: string
}

export interface RunSummary {
  run_id: string
  mode: string
  status: string
  success: boolean
  started_at?: string
  finished_at?: string
  duration?: number
}

// ---- 模板 (F012.4) ----
export interface TemplateSummary {
  id: string
  name: string
  category: string
  description?: string
  tags?: string[]
  usage_count: number
}

export interface TemplateDetail {
  id: string
  name: string
  category: string
  description?: string
  tags?: string[]
  flow: Flow
  usage_count: number
  created_at?: string
}

// ---- 调色板 (F012.5) ----
export interface PaletteNode {
  kind: string
  category: string
  label: string
  node_type: string
  params: PaletteParam[]
}

export interface PaletteParam {
  name: string
  type: string
  default?: any
  options?: string[]
}

export const api = {
  // ---- 工作流 CRUD ----
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

  palette: () => req<PaletteNode[]>('/api/palette'),

  execute: (id: string, mode: 'dry_run' | 'real' = 'dry_run') =>
    req<ExecuteResult>(`/api/workflows/${id}/execute?mode=${mode}`, {
      method: 'POST',
    }),

  // ---- 调度 API (F012.2) ----
  listTriggers: () => req<SchedulerTrigger[]>('/api/scheduler/triggers'),

  createTrigger: (data: {
    name: string
    target_workflow: string
    cron?: string
    interval_seconds?: number
    enabled?: boolean
  }) =>
    req<SchedulerTrigger>('/api/scheduler/triggers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateTrigger: (id: string, data: Partial<SchedulerTrigger>) =>
    req<SchedulerTrigger>(`/api/scheduler/triggers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteTrigger: (id: string) =>
    req<{ success: boolean }>(`/api/scheduler/triggers/${id}`, {
      method: 'DELETE',
    }),

  toggleTrigger: (id: string) =>
    req<SchedulerTrigger>(`/api/scheduler/triggers/${id}/toggle`, {
      method: 'POST',
    }),

  schedulerStatus: () => req<SchedulerStatus>('/api/scheduler/status'),

  // ---- 日志 API (F012.3) ----
  getRunsExtended: (wfId: string) =>
    req<RunSummary[]>(`/api/workflows/${wfId}/runs-extended`),

  getExecutionDetail: (runId: string) =>
    req<ExecutionDetail>(`/api/execution/${runId}/detail`),

  getNodeLogs: (runId: string) =>
    req<NodeLogDetail[]>(`/api/execution/${runId}/nodes`),

  getNodeScreenshot: (runId: string, nodeId: string) =>
    req<{ screenshot_b64: string }>(`/api/execution/${runId}/screenshot/${nodeId}`),

  // ---- 模板 API (F012.4) ----
  listTemplates: (params?: { category?: string; search?: string }) => {
    const qs = new URLSearchParams()
    if (params?.category) qs.set('category', params.category)
    if (params?.search) qs.set('search', params.search)
    const q = qs.toString()
    return req<TemplateSummary[]>(`/api/templates${q ? '?' + q : ''}`)
  },

  getTemplate: (id: string) => req<TemplateDetail>(`/api/templates/${id}`),

  createFromTemplate: (templateId: string) =>
    req<{ id: string; success: boolean }>(`/api/workflows/from-template/${templateId}`, {
      method: 'POST',
    }),

  saveAsTemplate: (wfId: string, data: { name?: string; category?: string; description?: string; tags?: string[] }) =>
    req<{ id: string; success: boolean }>(`/api/workflows/${wfId}/save-template`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // ---- 导入/导出 (F021) ----
  exportWorkflow: (id: string) =>
    req<{ id: string; name: string; flow: Flow; exported_at: string }>(`/api/workflows/${id}/export`),

  importWorkflow: (data: { name?: string; flow: Flow }) =>
    req<{ id: string; success: boolean }>('/api/workflows/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}
