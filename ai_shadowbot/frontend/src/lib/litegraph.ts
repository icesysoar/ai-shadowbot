// 统一从 @comfyorg/litegraph 重导出，作为本项目的 LiteGraph 接入层。
// Alpha Node 同款 ComfyUI 分支 LiteGraph.js，保留未来 vendored 替换能力。
export {
  LGraph,
  LGraphCanvas,
  LGraphNode,
  LiteGraph,
  LLink,
} from '@comfyorg/litegraph'

export type { LGraphNode as LGraphNodeType } from '@comfyorg/litegraph'
