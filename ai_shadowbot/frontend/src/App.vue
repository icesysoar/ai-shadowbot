<template>
  <div class="layout">
    <!-- 顶部工具栏 -->
    <header class="toolbar">
      <span class="brand">AI 影刀 · 工作流画布</span>
      <span class="wf-name">{{ workflowName || '未命名' }}</span>
      <span class="spacer" />
      <button @click="newWorkflow">新建</button>
      <button @click="save">保存</button>
      <button @click="loadDialog">加载</button>
      <button class="primary" :disabled="executing" @click="execute('dry_run')">执行(演练)</button>
      <button class="danger" :disabled="executing" @click="execute('real')">执行(真实)</button>
      <button @click="clearStatus">清状态</button>
    </header>

    <div class="body">
      <!-- 左：调色板 -->
      <aside class="palette">
        <h3>节点调色板</h3>
        <div v-for="(group, cat) in grouped" :key="cat" class="pal-group">
          <div class="pal-cat">{{ cat }}</div>
          <button
            v-for="spec in group"
            :key="spec.kind"
            class="pal-item"
            @click="addNode(spec.kind)"
          >
            {{ spec.label }}
          </button>
        </div>
      </aside>

      <!-- 中：画布 -->
      <main class="canvas-area">
        <GraphCanvas ref="canvasRef" @select="onSelect" @status-change="onStatus" />
        <div class="canvas-foot">
          节点 {{ stats.nodeCount }} · 连线 {{ stats.linkCount }}
        </div>
      </main>

      <!-- 右：属性 + AI 编译 + 状态 -->
      <aside class="side">
        <section class="panel">
          <h3>AI 编译</h3>
          <textarea v-model="aiQuery" rows="2" placeholder="用自然语言描述工作流，例如：打开记事本并输入 hello 然后截图" />
          <button class="primary" @click="aiCompile">编译到画布</button>
        </section>

        <section class="panel">
          <h3>属性</h3>
          <div v-if="selected" class="props">
            <div class="field">
              <label>标签</label>
              <input :value="selected.label" @input="onLabel" />
            </div>
            <div class="field" v-for="w in selected.widgets" :key="w.name">
              <label>{{ w.name }}</label>
              <select
                v-if="w.type === 'combo'"
                :value="w.value"
                @change="onWidget(w.name, $event)"
              >
                <option v-for="opt in comboOptions(w)" :key="opt" :value="opt">{{ opt }}</option>
              </select>
              <input
                v-else-if="w.type === 'number'"
                type="number"
                :value="w.value"
                @input="onWidget(w.name, $event)"
              />
              <input v-else type="text" :value="w.value" @input="onWidget(w.name, $event)" />
            </div>
            <div class="hint">类型：{{ selected.node_type }} · {{ selected.kind }}</div>
          </div>
          <div v-else class="empty">在画布中选择一个节点以编辑参数</div>
        </section>

        <section class="panel">
          <h3>执行状态</h3>
          <div v-if="logs.length" class="logs">
            <div v-for="(l, i) in logs" :key="i" :class="['log', l.status]">
              <span class="badge">{{ badge(l.status) }}</span>
              {{ l.node_id }} · {{ l.node_type }}
              <span v-if="l.error" class="err">⚠ {{ l.error }}</span>
            </div>
          </div>
          <div v-else class="empty">尚无执行记录</div>
        </section>
      </aside>
    </div>

    <!-- 加载对话框 -->
    <div v-if="showLoad" class="modal-mask" @click.self="showLoad = false">
      <div class="modal">
        <h3>加载工作流</h3>
        <div v-if="wfList.length" class="wf-list">
          <button v-for="w in wfList" :key="w.id" class="wf-row" @click="doLoad(w.id)">
            {{ w.name }} <span class="muted">{{ w.id }}</span>
          </button>
        </div>
        <div v-else class="empty">没有已保存的工作流</div>
        <button @click="showLoad = false">关闭</button>
      </div>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import GraphCanvas, { type NodeSnapshot } from './components/GraphCanvas.vue'
import { NODE_SPECS } from './nodes/specs'
import { api, type NodeLog } from './api-service'
import type { Flow } from './converters'

const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)
const selected = ref<NodeSnapshot | null>(null)
const stats = reactive({ nodeCount: 0, linkCount: 0 })
const aiQuery = ref('')
const logs = ref<NodeLog[]>([])
const executing = ref(false)
const workflowName = ref('')
const currentId = ref<string | null>(null)
const showLoad = ref(false)
const wfList = ref<{ id: string; name: string }[]>([])
const toast = ref('')

const grouped = computed(() => {
  const g: Record<string, typeof NODE_SPECS> = {}
  for (const s of NODE_SPECS) {
    ;(g[s.category] ||= []).push(s)
  }
  return g
})

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2200)
}

function onSelect(s: NodeSnapshot | null) {
  selected.value = s
}
function onStatus(d: { nodeCount: number; linkCount: number }) {
  stats.nodeCount = d.nodeCount
  stats.linkCount = d.linkCount
}

function addNode(kind: string) {
  canvasRef.value?.addNode(kind)
}

function onLabel(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (!selected.value) return
  selected.value.label = v
  canvasRef.value?.updateNode(selected.value.id, { label: v })
}

function comboOptions(w: { value: any }) {
  // combo 的候选值在 node 上未必暴露，这里用占位；真实选项由后端 schema 决定
  return Array.isArray(w.value) ? w.value : [w.value]
}

function onWidget(name: string, e: Event) {
  const el = e.target as HTMLInputElement | HTMLSelectElement
  let v: any = el.value
  if ((el as HTMLInputElement).type === 'number') v = Number(v)
  if (!selected.value) return
  const w = selected.value.widgets.find((x) => x.name === name)
  if (w) w.value = v
  canvasRef.value?.updateNode(selected.value.id, { widgets: { [name]: v } })
}

async function newWorkflow() {
  canvasRef.value?.clear()
  currentId.value = null
  workflowName.value = '未命名'
  logs.value = []
  canvasRef.value?.clearStatus()
  showToast('已新建空白工作流')
}

async function save() {
  const flow: Flow = canvasRef.value!.getFlow()
  try {
    if (currentId.value) {
      await api.updateWorkflow(currentId.value, flow)
      showToast('已保存')
    } else {
      const res = await api.createWorkflow(workflowName.value || '未命名工作流', flow)
      currentId.value = res.id
      showToast('已创建并保存')
    }
  } catch (err: any) {
    showToast('保存失败：' + err.message)
  }
}

async function loadDialog() {
  try {
    wfList.value = await api.listWorkflows()
  } catch {
    wfList.value = []
  }
  showLoad.value = true
}

async function doLoad(id: string) {
  try {
    const wf = await api.getWorkflow(id)
    canvasRef.value?.loadFlow(wf.flow)
    canvasRef.value?.clearStatus()
    currentId.value = wf.id
    workflowName.value = wf.name
    logs.value = []
    showToast('已加载：' + wf.name)
  } catch (err: any) {
    showToast('加载失败：' + err.message)
  }
  showLoad.value = false
}

async function aiCompile() {
  if (!aiQuery.value.trim()) {
    showToast('请输入自然语言描述')
    return
  }
  try {
    const flow = await api.compileToFlow(aiQuery.value)
    canvasRef.value?.loadFlow(flow)
    canvasRef.value?.clearStatus()
    currentId.value = null
    logs.value = []
    showToast('AI 编译完成，可保存')
  } catch (err: any) {
    showToast('编译失败：' + err.message)
  }
}

async function execute(mode: 'dry_run' | 'real') {
  // 先保存（确保后端有最新 flow）
  const flow = canvasRef.value!.getFlow()
  try {
    if (!currentId.value) {
      const res = await api.createWorkflow(workflowName.value || '未命名工作流', flow)
      currentId.value = res.id
    } else {
      await api.updateWorkflow(currentId.value, flow)
    }
  } catch (err: any) {
    showToast('保存失败：' + err.message)
    return
  }

  executing.value = true
  try {
    const res = await api.execute(currentId.value, mode)
    logs.value = res.execution.node_logs || []
    canvasRef.value?.applyStatus(logs.value)
    showToast(res.execution.success ? `执行成功（${mode}）` : `执行完成但有失败节点`)
  } catch (err: any) {
    showToast('执行失败：' + err.message)
  } finally {
    executing.value = false
  }
}

function clearStatus() {
  canvasRef.value?.clearStatus()
  logs.value = []
}

function badge(s: string) {
  return s === 'success' ? '✓' : s === 'failed' ? '✗' : s === 'running' ? '●' : '○'
}
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: var(--bg-0);
  color: var(--fg-0);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
}
.brand {
  font-weight: 600;
  color: var(--accent);
}
.wf-name {
  color: var(--fg-1);
  font-size: 13px;
}
.spacer {
  flex: 1;
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.palette {
  width: 180px;
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  padding: 10px;
  overflow-y: auto;
}
.palette h3,
.side h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pal-group {
  margin-bottom: 12px;
}
.pal-cat {
  font-size: 12px;
  color: var(--accent-2);
  margin-bottom: 4px;
}
.pal-item {
  display: block;
  width: 100%;
  text-align: left;
  margin-bottom: 4px;
  font-size: 12px;
  padding: 5px 8px;
}

.canvas-area {
  flex: 1;
  position: relative;
  min-width: 0;
}
.canvas-foot {
  position: absolute;
  bottom: 8px;
  left: 8px;
  font-size: 12px;
  color: var(--fg-1);
  background: rgba(0, 0, 0, 0.4);
  padding: 2px 8px;
  border-radius: 4px;
  pointer-events: none;
}

.side {
  width: 280px;
  background: var(--bg-1);
  border-left: 1px solid var(--border);
  padding: 10px;
  overflow-y: auto;
}
.panel {
  margin-bottom: 16px;
}
.field {
  margin-bottom: 8px;
}
.field label {
  display: block;
  font-size: 12px;
  color: var(--fg-1);
  margin-bottom: 3px;
}
.hint {
  font-size: 11px;
  color: var(--fg-1);
  margin-top: 6px;
}
.empty {
  font-size: 12px;
  color: var(--fg-1);
  padding: 8px 0;
}
.logs .log {
  font-size: 12px;
  padding: 4px 6px;
  border-radius: 4px;
  margin-bottom: 3px;
  background: var(--bg-2);
}
.log.success {
  border-left: 3px solid var(--success);
}
.log.failed {
  border-left: 3px solid var(--failed);
}
.log.running {
  border-left: 3px solid var(--running);
}
.badge {
  font-weight: bold;
  margin-right: 4px;
}
.err {
  color: var(--failed);
  margin-left: 4px;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  width: 360px;
  max-height: 70vh;
  overflow-y: auto;
}
.wf-list .wf-row {
  display: block;
  width: 100%;
  text-align: left;
  margin-bottom: 4px;
}
.muted {
  color: var(--fg-1);
  font-size: 11px;
}

.toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-3);
  color: var(--fg-0);
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid var(--accent);
  z-index: 60;
  font-size: 13px;
}
</style>
