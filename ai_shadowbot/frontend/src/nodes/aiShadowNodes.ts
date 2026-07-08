import { LGraphNode, LiteGraph } from '../lib/litegraph'
import { NODE_SPECS, SPEC_BY_KIND, type NodeSpec } from './specs'
import { categoryColor, statusTitleColor, statusBodyColor, statusBadge } from '../theme-store'

// 状态染色的节点基类工厂：按 spec 自动装配输入输出/widget，并支持执行状态着色
function makeAiNodeClass(spec: NodeSpec) {
  return class AiNode extends LGraphNode {
    static spec = spec

    constructor(title?: string) {
      super(title ?? spec.label)

      // 输入 / 输出插槽
      for (const inp of spec.inputs) this.addInput(inp || 'in', '*')
      for (const out of spec.outputs) this.addOutput(out || 'out', '*')

      // 参数控件
      for (const w of spec.widgets) {
        const opts = w.options ? { values: w.options } : undefined
        this.addWidget(w.type, w.name, w.default, () => {}, opts)
      }

      this.size = [210, 56 + spec.widgets.length * 26]
      this.properties = {
        kind: spec.kind,
        node_type: spec.node_type,
        label: spec.label,
      }
      this.color = categoryColor(spec.category)
    }

    override onDrawForeground(ctx: CanvasRenderingContext2D): void {
      const st = this.properties?.status
      if (!st) return
      const badge = statusBadge(st)
      if (!badge) return
      ctx.fillStyle = statusTitleColor(st) || '#888'
      ctx.font = 'bold 12px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(`${badge} ${st}`, this.size[0] / 2, this.size[1] - 8)
      ctx.textAlign = 'left'
    }
  }
}

// 注册所有节点到 LiteGraph（type = 'ai/<kind>'）
export function registerAiShadowNodes(lg: typeof LiteGraph): void {
  for (const spec of NODE_SPECS) {
    const Cls = makeAiNodeClass(spec)
    ;(lg as any).registerNodeType('ai/' + spec.kind, Cls as any)
  }
}

export { SPEC_BY_KIND }
