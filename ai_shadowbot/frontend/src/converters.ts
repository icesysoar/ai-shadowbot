import { LiteGraph } from './lib/litegraph'
import { SPEC_BY_KIND, type NodeSpec } from './nodes/specs'

// ---------------------------------------------------------------------------
// LiteGraph 图 ⇄ 后端 React Flow 格式（{nodes, edges}）互转
// 后端 canvas_api.flow_to_workflow 以 data.node_type / data.params 为准，
// 因此转换只须保证这两字段正确，无需改动后端。
// ---------------------------------------------------------------------------

export interface FlowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    label: string
    node_type: string
    params: Record<string, any>
  }
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  label?: string
}

export interface Flow {
  nodes: FlowNode[]
  edges: FlowEdge[]
}

function stripAtomic(p: Record<string, any>): Record<string, any> {
  const { atomic_action, ...rest } = p
  return rest
}

// LiteGraph 图 → 后端 Flow
export function graphToFlow(graph: any): Flow {
  const nodes: FlowNode[] = (graph.nodes || []).map((n: any) => {
    const kind: string = n.properties?.kind || String(n.type || '').replace('ai/', '')
    const spec: NodeSpec | undefined = SPEC_BY_KIND[kind]

    const params: Record<string, any> = {}
    if (n.widgets) {
      n.widgets.forEach((w: any, i: number) => {
        const wname = spec?.widgets[i]?.name
        if (wname) params[wname] = w.value
      })
    }

    const finalParams =
      spec?.node_type === 'atomic' ? { atomic_action: kind, ...params } : params

    return {
      id: String(n.id),
      type: kind,
      position: { x: Math.round(n.pos?.[0] ?? 0), y: Math.round(n.pos?.[1] ?? 0) },
      data: {
        label: n.properties?.label || n.title || kind,
        node_type: n.properties?.node_type || spec?.node_type || 'atomic',
        params: finalParams,
      },
    }
  })

  const edges: FlowEdge[] = (graph.links || []).map((l: any) => ({
    id: `e-${l.origin_id}-${l.target_id}-${l.origin_slot}`,
    source: String(l.origin_id),
    target: String(l.target_id),
    label: '',
  }))

  return { nodes, edges }
}

// 后端 Flow → LiteGraph 图
export function flowToGraph(graph: any, flow: Flow): void {
  graph.clear()
  for (const fn of flow.nodes || []) {
    const kind: string = fn.type
    const spec: NodeSpec | undefined = SPEC_BY_KIND[kind]
    const node = (LiteGraph as any).createNode('ai/' + kind)
    if (!node) continue

    node.id = fn.id
    node.pos = [fn.position?.x ?? 0, fn.position?.y ?? 0]
    node.properties = {
      kind,
      node_type: fn.data?.node_type || spec?.node_type || 'atomic',
      label: fn.data?.label || spec?.label || kind,
    }

    const params: Record<string, any> = fn.data?.params || {}
    const widgetParams = spec?.node_type === 'atomic' ? stripAtomic(params) : params
    if (node.widgets) {
      node.widgets.forEach((w: any, i: number) => {
        const wname = spec?.widgets[i]?.name
        if (wname && wname in widgetParams) w.value = widgetParams[wname]
      })
    }

    graph.add(node)
  }

  for (const fe of flow.edges || []) {
    try {
      graph.connect(fe.source, 0, fe.target, 0)
    } catch {
      /* 跳过不可连的边 */
    }
  }
}
