<template>
  <div class="scheduler-panel">
    <div class="panel-header">
      <h3>调度</h3>
      <button class="btn-sm" @click="showForm = !showForm">
        {{ showForm ? '取消' : '+ 新建触发器' }}
      </button>
    </div>

    <!-- 新建/编辑表单 -->
    <div v-if="showForm" class="trigger-form">
      <div class="field">
        <label>名称</label>
        <input v-model="form.name" placeholder="触发器名称" />
      </div>
      <div class="field">
        <label>目标工作流</label>
        <input v-model="form.target_workflow" placeholder="工作流 ID" />
      </div>
      <div class="field-row">
        <div class="field">
          <label>Cron 表达式</label>
          <input v-model="form.cron" placeholder="*/5 * * * *" />
        </div>
        <div class="field">
          <label>或间隔(秒)</label>
          <input v-model.number="form.interval_seconds" type="number" placeholder="300" />
        </div>
      </div>
      <button class="btn-primary" :disabled="!canSubmit" @click="submitTrigger">
        {{ editingId ? '更新' : '创建' }}
      </button>
    </div>

    <!-- 触发器列表 -->
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="error" class="err-msg">{{ error }}</div>
    <div v-else-if="!triggers.length" class="empty">暂无触发器</div>
    <div v-else class="trigger-list">
      <div
        v-for="t in triggers"
        :key="t.id"
        :class="['trigger-card', { disabled: !t.enabled }]"
      >
        <div class="trigger-head">
          <span class="trigger-name">{{ t.name }}</span>
          <label class="toggle-switch">
            <input
              type="checkbox"
              :checked="t.enabled"
              @change="toggle(t)"
            />
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="trigger-meta">
          <span class="meta-item">{{ t.cron || `${t.interval_seconds}s` }}</span>
          <span class="meta-item">→ {{ t.target_workflow }}</span>
        </div>
        <div v-if="t.next_run" class="trigger-next">
          下次执行: {{ formatTime(t.next_run) }}
        </div>
        <div class="trigger-actions">
          <button class="btn-sm" @click="editTrigger(t)">编辑</button>
          <button class="btn-sm btn-danger" @click="removeTrigger(t.id)">删除</button>
        </div>
      </div>
    </div>

    <!-- 调度器状态 -->
    <div v-if="status" class="scheduler-status">
      <span :class="['status-dot', status.running ? 'on' : 'off']"></span>
      调度器 {{ status.running ? '运行中' : '已停止' }}
      · {{ status.enabled_count }}/{{ status.trigger_count }} 启用
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type SchedulerTrigger, type SchedulerStatus } from '../api-service'

const triggers = ref<SchedulerTrigger[]>([])
const status = ref<SchedulerStatus | null>(null)
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const editingId = ref<string | null>(null)

const form = ref({
  name: '',
  target_workflow: '',
  cron: '',
  interval_seconds: null as number | null,
})

const canSubmit = computed(() => {
  return form.value.name.trim() && form.value.target_workflow.trim() && (form.value.cron.trim() || form.value.interval_seconds)
})

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function fetchTriggers() {
  loading.value = true
  error.value = ''
  try {
    const [tList, s] = await Promise.all([
      api.listTriggers(),
      api.schedulerStatus(),
    ])
    triggers.value = tList
    status.value = s
  } catch (e: any) {
    error.value = '加载失败：' + e.message
  } finally {
    loading.value = false
  }
}

async function submitTrigger() {
  if (!canSubmit.value) return
  try {
    const data = {
      name: form.value.name.trim(),
      target_workflow: form.value.target_workflow.trim(),
      cron: form.value.cron.trim() || undefined,
      interval_seconds: form.value.interval_seconds || undefined,
      enabled: true,
    }
    if (editingId.value) {
      await api.updateTrigger(editingId.value, data)
    } else {
      await api.createTrigger(data)
    }
    showForm.value = false
    editingId.value = null
    resetForm()
    await fetchTriggers()
  } catch (e: any) {
    error.value = '操作失败：' + e.message
  }
}

function editTrigger(t: SchedulerTrigger) {
  editingId.value = t.id
  form.value = {
    name: t.name,
    target_workflow: t.target_workflow,
    cron: t.cron || '',
    interval_seconds: t.interval_seconds || null,
  }
  showForm.value = true
}

function resetForm() {
  form.value = { name: '', target_workflow: '', cron: '', interval_seconds: null }
  editingId.value = null
}

async function toggle(t: SchedulerTrigger) {
  try {
    await api.toggleTrigger(t.id)
    t.enabled = !t.enabled
    await fetchTriggers()
  } catch (e: any) {
    error.value = '切换失败：' + e.message
  }
}

async function removeTrigger(id: string) {
  if (!confirm('确定删除此触发器？')) return
  try {
    await api.deleteTrigger(id)
    await fetchTriggers()
  } catch (e: any) {
    error.value = '删除失败：' + e.message
  }
}

onMounted(fetchTriggers)
</script>

<style scoped>
.scheduler-panel {
  font-size: 12px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.panel-header h3 {
  margin: 0;
  font-size: 13px;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.trigger-form {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 10px;
}
.field {
  margin-bottom: 8px;
}
.field label {
  display: block;
  font-size: 11px;
  color: var(--fg-1);
  margin-bottom: 2px;
}
.field input {
  width: 100%;
  box-sizing: border-box;
}
.field-row {
  display: flex;
  gap: 8px;
}
.field-row .field {
  flex: 1;
}

.trigger-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}
.trigger-card {
  background: var(--bg-2);
  border-radius: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
}
.trigger-card.disabled {
  opacity: 0.5;
}
.trigger-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.trigger-name {
  font-weight: 600;
}
.trigger-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 2px;
}
.meta-item {
  background: var(--bg-0);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 11px;
  color: var(--accent-2);
}
.trigger-next {
  font-size: 11px;
  color: var(--fg-1);
  margin-bottom: 4px;
}
.trigger-actions {
  display: flex;
  gap: 4px;
}

/* Toggle switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 32px;
  height: 18px;
}
.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: #555;
  border-radius: 18px;
  transition: 0.2s;
}
.toggle-slider::before {
  content: '';
  position: absolute;
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background: white;
  border-radius: 50%;
  transition: 0.2s;
}
.toggle-switch input:checked + .toggle-slider {
  background: var(--accent);
}
.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(14px);
}

.scheduler-status {
  margin-top: 10px;
  padding: 6px 8px;
  background: var(--bg-2);
  border-radius: 4px;
  font-size: 11px;
  color: var(--fg-1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.on { background: var(--success); }
.status-dot.off { background: #555; }

.btn-sm {
  font-size: 11px;
  padding: 3px 8px;
}
.btn-primary {
  font-size: 12px;
  padding: 5px 12px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  width: 100%;
}
.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-danger {
  color: var(--failed);
  border-color: var(--failed);
}
.empty {
  font-size: 12px;
  color: var(--fg-1);
  padding: 12px 0;
}
.err-msg {
  color: var(--failed);
  font-size: 12px;
  padding: 4px 0;
}
</style>
