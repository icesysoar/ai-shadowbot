<template>
  <div class="log-panel">
    <h3>执行日志</h3>

    <!-- 工作流 ID 输入 -->
    <div class="wf-select">
      <input
        v-model="wfId"
        placeholder="工作流 ID（或选择已加载）"
        @keyup.enter="fetchRuns"
      />
      <button class="btn-sm" @click="fetchRuns" :disabled="!wfId.trim()">查询</button>
    </div>

    <!-- 执行历史列表 -->
    <div v-if="loadingRuns" class="empty">加载中...</div>
    <div v-else-if="runsError" class="err-msg">{{ runsError }}</div>
    <div v-else-if="!runs.length" class="empty">暂无执行记录</div>
    <div v-else class="runs-list">
      <div
        v-for="r in runs"
        :key="r.run_id"
        :class="['run-row', { active: selectedRunId === r.run_id }]"
        @click="selectRun(r.run_id)"
      >
        <span :class="['status-badge', r.status]">
          {{ badge(r.status) }}
        </span>
        <span class="run-mode">{{ r.mode }}</span>
        <span class="run-time">{{ formatTime(r.started_at) }}</span>
        <span v-if="r.duration" class="run-dur">{{ r.duration }}ms</span>
      </div>
    </div>

    <!-- 执行详情 -->
    <div v-if="selectedRunId" class="detail-section">
      <h4>
        运行详情
        <span class="run-id">{{ selectedRunId.slice(0, 8) }}...</span>
      </h4>

      <div v-if="loadingDetail" class="empty">加载中...</div>
      <div v-else-if="detailError" class="err-msg">{{ detailError }}</div>
      <div v-else-if="detail" class="node-timeline">
        <div
          v-for="nl in detail.node_logs"
          :key="nl.node_id"
          :class="['timeline-item', nl.status]"
        >
          <div class="tl-head">
            <span :class="['status-badge', nl.status]">{{ badge(nl.status) }}</span>
            <span class="node-label">{{ nl.node_type }} · {{ nl.node_id.slice(0, 8) }}</span>
            <span v-if="nl.duration" class="tl-dur">{{ nl.duration }}ms</span>
          </div>
          <div v-if="nl.error" class="tl-error">⚠ {{ nl.error }}</div>
          <div class="tl-time">
            {{ formatTime(nl.started_at) }}
            <span v-if="nl.finished_at"> → {{ formatTime(nl.finished_at) }}</span>
          </div>
          <button
            v-if="nl.screenshot_b64"
            class="btn-sm screenshot-btn"
            @click="viewScreenshot(nl.screenshot_b64)"
          >
            查看截图
          </button>
        </div>
      </div>
    </div>

    <!-- 截图预览 -->
    <div v-if="screenshotSrc" class="screenshot-modal" @click.self="screenshotSrc = null">
      <img :src="screenshotSrc" alt="节点截图" />
      <button class="close-btn" @click="screenshotSrc = null">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api, type RunSummary, type ExecutionDetail } from '../api-service'

const props = defineProps<{
  currentWorkflowId?: string | null
}>()

const wfId = ref('')
const runs = ref<RunSummary[]>([])
const loadingRuns = ref(false)
const runsError = ref('')
const selectedRunId = ref<string | null>(null)
const detail = ref<ExecutionDetail | null>(null)
const loadingDetail = ref(false)
const detailError = ref('')
const screenshotSrc = ref<string | null>(null)

// 当 props 变化时自动填充 wfId
watch(() => props.currentWorkflowId, (id) => {
  if (id && !wfId.value) {
    wfId.value = id
    fetchRuns()
  }
})

function badge(s: string): string {
  switch (s) {
    case 'success': return '✓'
    case 'failed': return '✗'
    case 'running': return '●'
    case 'skipped': return '○'
    default: return '·'
  }
}

function formatTime(iso?: string): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

async function fetchRuns() {
  if (!wfId.value.trim()) return
  loadingRuns.value = true
  runsError.value = ''
  try {
    runs.value = await api.getRunsExtended(wfId.value.trim())
  } catch (e: any) {
    runsError.value = '加载失败：' + e.message
    runs.value = []
  } finally {
    loadingRuns.value = false
  }
}

async function selectRun(runId: string) {
  selectedRunId.value = runId
  loadingDetail.value = true
  detailError.value = ''
  detail.value = null
  try {
    detail.value = await api.getExecutionDetail(runId)
  } catch (e: any) {
    detailError.value = '加载详情失败：' + e.message
  } finally {
    loadingDetail.value = false
  }
}

function viewScreenshot(b64: string) {
  screenshotSrc.value = `data:image/png;base64,${b64}`
}
</script>

<style scoped>
.log-panel {
  font-size: 12px;
}
.log-panel h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.log-panel h4 {
  margin: 10px 0 6px;
  font-size: 12px;
  color: var(--fg-1);
}
.run-id {
  font-size: 11px;
  color: var(--accent-2);
  font-family: monospace;
}

.wf-select {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}
.wf-select input {
  flex: 1;
  font-size: 12px;
  padding: 4px 8px;
}

.runs-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 180px;
  overflow-y: auto;
  margin-bottom: 8px;
}
.run-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  background: var(--bg-2);
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
}
.run-row:hover {
  border-color: var(--border);
}
.run-row.active {
  border-color: var(--accent);
  background: rgba(74, 158, 255, 0.08);
}
.run-mode {
  background: var(--bg-0);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  text-transform: uppercase;
}
.run-time {
  flex: 1;
  font-size: 11px;
  color: var(--fg-1);
}
.run-dur {
  font-size: 11px;
  color: var(--accent-2);
  font-family: monospace;
}

.status-badge {
  font-weight: bold;
  font-size: 11px;
  width: 16px;
  text-align: center;
}
.status-badge.success { color: var(--success); }
.status-badge.failed { color: var(--failed); }
.status-badge.running { color: var(--running); }

.detail-section {
  border-top: 1px solid var(--border);
  padding-top: 4px;
}

.node-timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
}
.timeline-item {
  background: var(--bg-2);
  border-radius: 4px;
  padding: 6px 8px;
  border-left: 3px solid transparent;
}
.timeline-item.success { border-left-color: var(--success); }
.timeline-item.failed { border-left-color: var(--failed); }
.timeline-item.running { border-left-color: var(--running); }
.tl-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.node-label {
  flex: 1;
}
.tl-dur {
  font-size: 11px;
  color: var(--accent-2);
  font-family: monospace;
}
.tl-error {
  color: var(--failed);
  font-size: 11px;
  margin-top: 2px;
}
.tl-time {
  font-size: 10px;
  color: var(--fg-1);
  margin-top: 2px;
}

.screenshot-btn {
  margin-top: 4px;
  font-size: 11px;
}

.screenshot-modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.screenshot-modal img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.close-btn {
  position: absolute;
  top: 16px;
  right: 24px;
  font-size: 20px;
  background: none;
  border: none;
  color: #fff;
  cursor: pointer;
}

.btn-sm {
  font-size: 11px;
  padding: 3px 8px;
}
.empty {
  font-size: 12px;
  color: var(--fg-1);
  padding: 8px 0;
}
.err-msg {
  color: var(--failed);
  font-size: 12px;
  padding: 4px 0;
}
</style>
