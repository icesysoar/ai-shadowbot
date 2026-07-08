<template>
  <div
    ref="wrapperRef"
    class="graph-canvas-wrapper"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <canvas ref="canvasRef" />
    <div v-if="isLoading" class="alpha-loading-overlay">
      <div class="alpha-loading-spinner"></div>
      <span class="alpha-loading-text">初始化画布...</span>
    </div>
    <div v-if="error" class="alpha-error-overlay">
      <div class="alpha-error-box">
        <strong>画布初始化失败</strong>
        <pre>{{ error }}</pre>
      </div>
    </div>
    <div v-if="dragOver" class="drag-hint">释放以放置节点</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { LGraph, LGraphCanvas, LiteGraph } from '../lib/litegraph'
import { registerAiShadowNodes } from '../nodes/aiShadowNodes'
import { graphToFlow, flowToGraph, type Flow } from '../converters'
import { statusTitleColor, statusBodyColor } from '../theme-store'

const emit = defineEmits<{
  (e: 'select', node: NodeSnapshot | null): void
  (e: 'status-change', data: { nodeCount: number; linkCount: number }): void
}>()

export interface NodeSnapshot {
  id: string
  kind: string
  label: string
  node_type: string
  widgets: { name: string; type: string; value: any }[]
}

const canvasRef = ref<HTMLCanvasElement | null>(null)
const wrapperRef = ref<HTMLDivElement | null>(null)
const isLoading = ref(true)
const error = ref<string | null>(null)
const dragOver = ref(false)

let graph: LGraph | null = null
let graphCanvas: LGraphCanvas | null = null
let ro: ResizeObserver | null = null
let rafId = 0

function snapshot(node: any): NodeSnapshot {
  return {
    id: String(node.id),
    kind: node.properties?.kind || String(node.type || '').replace('ai/', ''),
    label: node.properties?.label || node.title || '',
    node_type: node.properties?.node_type || 'atomic',
    widgets: (node.widgets || []).map((w: any) => ({
      name: w.name,
      type: w.type,
      value: w.value,
    })),
  }
}

function updateStatus() {
  if (!graph) return
  emit('status-change', {
    nodeCount: graph.nodes.length,
    linkCount: graph.links ? Object.keys(graph.links).length : 0,
  })
}

// ---- DPR 精细优化 (F012.6) ----
// 强制 canvas 物理像素 = clientWidth/Height * devicePixelRatio
// 并在 LiteGraph resizeCanvas 后确保 ctx.setTransform 正确应用
function ensureDPR() {
  if (!canvasRef.value || !wrapperRef.value) return
  const el = canvasRef.value
  const parent = wrapperRef.value
  const dpr = window.devicePixelRatio || 1
  const w = parent.clientWidth
  const h = parent.clientHeight
  const pw = Math.floor(w * dpr)
  const ph = Math.floor(h * dpr)

  if (el.width !== pw || el.height !== ph) {
    el.width = pw
    el.height = ph
    // 确保 LiteGraph 的 ctx 也正确缩放
    // 注意：不设 style.width/height，CSS 100% 自动跟随
    const ctx = el.getContext('2d')
    if (ctx) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    if (graphCanvas) {
      graphCanvas.setDirty(true, true)
    }
  }
}

// 画布尺寸跟随容器
function fitCanvas() {
  // 先强制 DPR 物理像素
  ensureDPR()
  // 然后让 LiteGraph 内部适配新尺寸
  if (!graphCanvas) return
  try {
    graphCanvas.resizeCanvas()
  } catch {
    /* ignore */
  }
  // resizeCanvas 后再次确保 transform 正确（防止 LiteGraph 内部用 ctx.scale 累积）
  const ctx = canvasRef.value?.getContext('2d')
  if (ctx) {
    const dpr = window.devicePixelRatio || 1
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
}

function scheduleFit() {
  requestAnimationFrame(() => requestAnimationFrame(fitCanvas))
}

// ---- 拖拽放置 (F012.1) ----
function onDragOver(e: DragEvent) {
  // 只接受 palette 节点拖拽
  if (e.dataTransfer?.types.includes('text/plain')) {
    dragOver.value = true
  }
}

function onDragLeave() {
  dragOver.value = false
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const kind = e.dataTransfer?.getData('text/plain')
  if (!kind) return
  addNodeAtPos(kind, e.clientX, e.clientY)
}

function addNodeAtPos(kind: string, clientX: number, clientY: number): void {
  if (!graph) return
  const node = (LiteGraph as any).createNode('ai/' + kind)
  if (!node) return
  const rect = wrapperRef.value?.getBoundingClientRect()
  if (rect && graphCanvas) {
    const canvasPos = graphCanvas.convertOffsetToCanvas(
      clientX - rect.left,
      clientY - rect.top,
    )
    node.pos = [Math.round(canvasPos.x - 100), Math.round(canvasPos.y - 30)]
  } else {
    node.pos = [120, 120]
  }
  graph.add(node)
  updateStatus()
}

onMounted(() => {
  error.value = null
  if (!canvasRef.value || !wrapperRef.value) return
  try {
    registerAiShadowNodes(LiteGraph as any)

    graph = new LGraph()
    graphCanvas = new LGraphCanvas(canvasRef.value, graph)

    // 初始 DPR 设置
    ensureDPR()

    // 0.17 事件系统已改为 addEventListener（且事件名为 kebab-case），
    // 旧版 graph.on / graphCanvas.on 已不存在，调用会抛 TypeError。
    // 节点增删/连线已在 addNode/clear/loadFlow 中手动触发 updateStatus，
    // 选中态通过轮询 selectedItems（Set<Positionable>）实现，无需依赖事件名。
    setTimeout(() => {
      isLoading.value = false
      scheduleFit()
    }, 400)
  } catch (e) {
    error.value = e instanceof Error ? `${e.name}: ${e.message}` : String(e)
    isLoading.value = false
    return
  }

  // 选中态轮询（graphCanvas.selectedItems: Set<Positionable>）
  let lastSelId: string | null = null
  const pollSelection = () => {
    if (!graphCanvas) return
    const sel = (graphCanvas as any).selectedItems as Set<any> | undefined
    let curId: string | null = null
    if (sel && sel.size) {
      for (const item of sel) {
        if (item && item.properties && item.properties.kind) {
          curId = String(item.id)
          break
        }
      }
    }
    if (curId !== lastSelId) {
      lastSelId = curId
      if (curId && graph) {
        const node = graph.getNodeById(curId)
        if (node) {
          emit('select', snapshot(node))
          return
        }
      }
      emit('select', null)
    }
  }
  const pollLoop = () => {
    pollSelection()
    rafId = requestAnimationFrame(pollLoop)
  }
  rafId = requestAnimationFrame(pollLoop)

  // 容器尺寸变化 → 重算画布（double rAF 等 DOM 稳定）
  ro = new ResizeObserver(scheduleFit)
  ro.observe(wrapperRef.value)

  // 监听 DPR 变化（如拖到不同 DPI 的显示器）
  const onDprChange = () => scheduleFit()
  window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`).addEventListener('change', onDprChange)

  ;(window as any).alphaGraph = graph
  ;(window as any).alphaGraphCanvas = graphCanvas
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  ro?.disconnect()
  if (graphCanvas) {
    ;(graphCanvas as any).destroy?.()
    graphCanvas = null
  }
  graph = null
})

// ---- 对外 API ----
function addNode(kind: string): void {
  if (!graph) return
  const node = (LiteGraph as any).createNode('ai/' + kind)
  if (!node) return
  // 视口中心附近放置（兜底：点击添加）
  const center = graphCanvas
    ? graphCanvas.convertOffsetToCanvas(
        (wrapperRef.value?.clientWidth || 400) / 2,
        (wrapperRef.value?.clientHeight || 300) / 2,
      )
    : { x: 120, y: 120 }
  node.pos = [Math.round(center.x - 100), Math.round(center.y - 30)]
  graph.add(node)
  updateStatus()
}

function loadFlow(flow: Flow): void {
  if (!graph) return
  flowToGraph(graph, flow)
  graphCanvas?.setDirty(true)
  updateStatus()
}

function getFlow(): Flow {
  return graph ? graphToFlow(graph) : { nodes: [], edges: [] }
}

function clear(): void {
  graph?.clear()
  updateStatus()
}

function updateNode(id: string, patch: { label?: string; widgets?: Record<string, any> }): void {
  const node = graph?.getNodeById(id)
  if (!node) return
  if (patch.label !== undefined) node.properties = { ...node.properties, label: patch.label }
  if (patch.widgets && node.widgets) {
    node.widgets.forEach((w: any) => {
      if (w.name in patch.widgets!) w.value = patch.widgets![w.name]
    })
  }
  node.setDirtyCanvas(true, true)
}

// 执行后状态着色
function applyStatus(logs: { node_id: string; status: string }[]): void {
  if (!graph) return
  for (const log of logs) {
    const node = graph.getNodeById(log.node_id)
    if (!node) continue
    node.properties = { ...node.properties, status: log.status }
    const t = statusTitleColor(log.status)
    const b = statusBodyColor(log.status)
    if (t) node.color = t
    if (b) node.bgcolor = b
    node.setDirtyCanvas(true, true)
  }
  graphCanvas?.setDirty(true)
}

function clearStatus(): void {
  if (!graph) return
  for (const node of graph.nodes) {
    if (node.properties?.status) {
      delete node.properties.status
      node.color = undefined
      node.bgcolor = undefined
      node.setDirtyCanvas(true, true)
    }
  }
  graphCanvas?.setDirty(true)
}

defineExpose({ addNode, addNodeAtPos, loadFlow, getFlow, clear, updateNode, applyStatus, clearStatus })
</script>

<style scoped>
.graph-canvas-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
  background: #1e1e1e;
  overflow: hidden;
}

.graph-canvas-wrapper canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.drag-hint {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(74, 158, 255, 0.85);
  color: #fff;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
  pointer-events: none;
  z-index: 10;
  animation: pulse-hint 1.2s ease-in-out infinite;
}

@keyframes pulse-hint {
  0%, 100% { opacity: 0.75; }
  50% { opacity: 1; }
}

.alpha-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #1e1e1e;
  color: #9d9d9d;
  z-index: 5;
}

.alpha-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #3c3c3c;
  border-top-color: #4a9eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.alpha-error-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #1e1e1e;
  color: #ff8a80;
  z-index: 6;
}

.alpha-error-box {
  max-width: 90%;
  border: 1px solid #5a2a2a;
  border-radius: 8px;
  padding: 16px 18px;
  background: #2a1a1a;
}

.alpha-error-box strong {
  display: block;
  margin-bottom: 8px;
  color: #ff5252;
}

.alpha-error-box pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  font-family: Consolas, monospace;
  color: #ffb3ab;
}
</style>
