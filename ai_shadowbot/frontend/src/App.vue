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
      <button @click="doExport" :disabled="!currentId">导出</button>
      <button @click="triggerImport">导入</button>
      <input ref="importInput" type="file" accept=".json" style="display:none" @change="doImport" />
      <button class="primary" :disabled="executing" @click="execute('dry_run')">执行(演练)</button>
      <button class="danger" :disabled="executing" @click="execute('real')">执行(真实)</button>
      <button @click="clearStatus">清状态</button>
    </header>

    <div class="body">
      <!-- 左：调色板（支持拖拽 + 点击） -->
      <aside class="palette">
        <h3>节点调色板</h3>
        <div v-for="(group, cat) in grouped" :key="cat" class="pal-group">
          <div class="pal-cat">{{ cat }}</div>
          <button
            v-for="spec in group"
            :key="spec.kind"
            class="pal-item"
            draggable="true"
            @dragstart="onDragStart($event, spec.kind)"
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

      <!-- 右：Tab 面板 -->
      <aside class="side">
        <div class="tabs">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            :class="['tab-btn', { active: activeTab === tab.id }]"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="tab-content">
          <!-- 概览面板 -->
          <DashboardPanel v-if="activeTab === 'dashboard'" />

          <!-- 调度面板 -->
          <SchedulerPanel v-if="activeTab === 'scheduler'" />

          <!-- 日志面板 -->
          <LogPanel
            v-if="activeTab === 'logs'"
            :current-workflow-id="currentId"
          />

          <!-- 模板面板 -->
          <TemplatePanel
            v-if="activeTab === 'templates'"
            :current-workflow-id="currentId"
            @use-template="onUseTemplate"
          />

          <!-- 变量面板 -->
          <VariablePanel
            v-if="activeTab === 'variables'"
            :get-flow="() => canvasRef?.getFlow()"
          />

          <!-- AI 编译 + 属性 + 状态面板（原有面板合并） -->
          <div v-if="activeTab === 'properties'">
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
          </div>
        </div>
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
import { ref, reactive, computed, onMounted } from 'vue'
import GraphCanvas, { type NodeSnapshot } from './components/GraphCanvas.vue'
import DashboardPanel from './components/DashboardPanel.vue'
import SchedulerPanel from './components/SchedulerPanel.vue'
import LogPanel from './components/LogPanel.vue'
import TemplatePanel from './components/TemplatePanel.vue'
import VariablePanel from './components/VariablePanel.vue'
import { NODE_SPECS } from './nodes/specs'
import { api, type NodeLog, type PaletteNode } from './api-service'
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
const importInput = ref<HTMLInputElement | null>(null)

// ---- Tab 系统 ----
const tabs = [
  { id: 'dashboard', label: '概览' },
  { id: 'scheduler', label: '调度' },
  { id: 'logs', label: '日志' },
  { id: 'templates', label: '模板' },
  { id: 'variables', label: '变量' },
  { id: 'properties', label: '属性' },
]
const activeTab = ref('properties')

// ---- Palette 数据 (F012.5) ----
const paletteNodes = ref<PaletteNode[]>([])

onMounted(async () => {
  try {
    paletteNodes.value = await api.palette()
  } catch {
    // palette 加载失败不阻塞，combo 回退到 spec 内置 options
  }
})

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
  // 选择节点时自动切到属性 tab
  if (s) activeTab.value = 'properties'
}

function onStatus(d: { nodeCount: number; linkCount: number }) {
  stats.nodeCount = d.nodeCount
  stats.linkCount = d.linkCount
}

// ---- 拖拽 (F012.1) ----
function onDragStart(e: DragEvent, kind: string) {
  e.dataTransfer?.setData('text/plain', kind)
  e.dataTransfer!.effectAllowed = 'move'
}

// ---- 点击添加（兜底） ----
function addNode(kind: string) {
  canvasRef.value?.addNode(kind)
}

function onLabel(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (!selected.value) return
  selected.value.label = v
  canvasRef.value?.updateNode(selected.value.id, { label: v })
}

// ---- Combo 选项对接后端 palette (F012.5) ----
function comboOptions(w: { name: string; value: any; type: string }) {
  // 1) 从后端 palette 按 kind 匹配
  if (selected.value && paletteNodes.value.length) {
    const pn = paletteNodes.value.find((p) => p.kind === selected.value!.kind)
    if (pn) {
      const param = pn.params?.find((p) => p.name === w.name)
      if (param?.options?.length) {
        return param.options
      }
    }
  }
  // 2) 从本地 spec 中取 options（fallback）
  const spec = NODE_SPECS.find((s) => s.kind === selected.value?.kind)
  if (spec) {
    const ws = spec.widgets.find((sw) => sw.name === w.name)
    if (ws?.options?.length) return ws.options
  }
  // 3) 最后兜底：当前值作为唯一条目
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

// ---- 模板使用回调 ----
async function onUseTemplate(templateId: string) {
  try {
    const result = await api.createFromTemplate(templateId)
    if (result.id) {
      // 加载新建的工作流
      const wf = await api.getWorkflow(result.id)
      canvasRef.value?.loadFlow(wf.flow)
      canvasRef.value?.clearStatus()
      currentId.value = wf.id
      workflowName.value = wf.name
      logs.value = []
      showToast('已从模板创建：' + wf.name)
    }
  } catch (err: any) {
    showToast('使用模板失败：' + err.message)
  }
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

// ---- F021 导入/导出 ----
async function doExport() {
  if (!currentId.value) return
  try {
    const data = await api.exportWorkflow(currentId.value)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${data.name || 'workflow'}.json`
    a.click(); URL.revokeObjectURL(url)
    showToast('已导出：' + data.name)
  } catch (err: any) { showToast('导出失败：' + err.message) }
}
function triggerImport() { importInput.value?.click() }
async function doImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const res = await api.importWorkflow(data)
    if (res.id) {
      const wf = await api.getWorkflow(res.id)
      canvasRef.value?.loadFlow(wf.flow)
      canvasRef.value?.clearStatus()
      currentId.value = wf.id; workflowName.value = wf.name; logs.value = []
      showToast('已导入：' + wf.name)
    }
  } catch (err: any) { showToast('导入失败：' + err.message) }
  (e.target as HTMLInputElement).value = ''
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

/* ---- 调色板 ---- */
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
  cursor: grab;
}
.pal-item:active {
  cursor: grabbing;
}

/* ---- 画布 ---- */
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

/* ---- 右侧面板 ---- */
.side {
  width: 280px;
  background: var(--bg-1);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ---- Tab 栏 ---- */
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.tab-btn {
  flex: 1;
  padding: 8px 0;
  font-size: 12px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--fg-1);
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:hover {
  color: var(--fg-0);
}
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.tab-content {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  min-height: 0;
}

/* ---- 面板内部 ---- */
.panel {
  margin-bottom: 16px;
}
.panel h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
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
.field input,
.field select {
  width: 100%;
  box-sizing: border-box;
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

/* ---- 执行日志 ---- */
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

/* ---- 加载对话框 ---- */
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
