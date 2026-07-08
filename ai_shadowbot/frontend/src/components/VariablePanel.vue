<template>
  <div class="var-panel">
    <div class="var-header">
      <h4>变量列表</h4>
      <button class="small" @click="showAdd = true">+ 添加</button>
    </div>

    <table v-if="variables.length" class="var-table">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>引用次数</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="v in variables" :key="v.name">
          <td><code>{<!-- -->{variables.{{ v.name }}}}</code></td>
          <td><span class="type-tag">{{ v.type }}</span></td>
          <td>{{ v.refs }}</td>
          <td><button class="small danger" @click="removeVar(v.name)">删除</button></td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">
      当前工作流未引用任何变量。<br/>
      在节点参数中使用 {<!-- -->{variables.name}} 即可自动检测。
    </div>

    <!-- 添加弹窗 -->
    <div v-if="showAdd" class="modal-mask" @click.self="showAdd = false">
      <div class="modal">
        <h4>添加变量</h4>
        <div class="field">
          <label>变量名</label>
          <input v-model="newName" placeholder="my_var" />
        </div>
        <div class="field">
          <label>类型</label>
          <select v-model="newType">
            <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="primary" @click="doAdd" :disabled="!newName.trim()">确定</button>
          <button @click="showAdd = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Flow } from '../converters'
import { NODE_SPECS } from '../nodes/specs'

const props = defineProps<{ getFlow: () => Flow | null }>()

const TYPES = ['str', 'int', 'bool', 'list', 'dict']
const variables = ref<{ name: string; type: string; refs: number }[]>([])
const showAdd = ref(false)
const newName = ref('')
const newType = ref('str')
const toast = ref('')

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2000)
}

function refresh() {
  const flow = props.getFlow?.()
  if (!flow) { variables.value = []; return }
  const seen = new Map<string, { type: string; refs: number }>()
  const RE = /\{\{variables\.(\w+)\}\}/g
  for (const n of flow.nodes || []) {
    const text = JSON.stringify(n.data?.params || {})
    let m: RegExpExecArray | null
    while ((m = RE.exec(text)) !== null) {
      const name = m[1]
      const spec = NODE_SPECS.find(s => s.kind === (n.type || '').replace('ai/', ''))
      const widget = spec?.widgets?.find(w => w.name === name)
      const type = widget?.type === 'number' ? 'int' : widget?.type === 'toggle' ? 'bool' : 'str'
      if (seen.has(name)) {
        seen.get(name)!.refs++
      } else {
        seen.set(name, { type, refs: 1 })
      }
    }
  }
  variables.value = Array.from(seen.entries()).map(([name, info]) => ({ name, type: info.type, refs: info.refs }))
}

function removeVar(name: string) {
  variables.value = variables.value.filter(v => v.name !== name)
  showToast(`已移除变量: ${name}`)
  // 注意: 这不会修改节点中的 {{variables.xxx}} 引用，仅从面板移除
}

function doAdd() {
  if (!newName.value.trim()) return
  if (variables.value.find(v => v.name === newName.value.trim())) {
    showToast('变量名已存在')
    return
  }
  variables.value.push({ name: newName.value.trim(), type: newType.value, refs: 0 })
  showAdd.value = false
  newName.value = ''
  newType.value = 'str'
  showToast(`已添加变量: ${newName.value}`)
}

// 定期刷新（画布变更时自动检测新变量）
let timer = 0
watch(() => props.getFlow?.(), () => { clearTimeout(timer); timer = window.setTimeout(refresh, 400) }, { deep: true })
</script>

<style scoped>
.var-panel { padding: 4px 0; }
.var-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.var-header h4 { margin: 0; font-size: 13px; color: var(--fg-1); text-transform: uppercase; }
.var-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.var-table th { text-align: left; font-size: 11px; color: var(--fg-1); padding: 4px 6px; border-bottom: 1px solid var(--border); }
.var-table td { padding: 5px 6px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.var-table code { font-size: 12px; background: var(--bg-2); padding: 1px 4px; border-radius: 3px; }
.type-tag { font-size: 11px; background: var(--accent); color: #fff; padding: 1px 6px; border-radius: 3px; }
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; width: 300px; }
.modal h4 { margin: 0 0 12px; }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 12px; color: var(--fg-1); margin-bottom: 4px; }
.field input, .field select { width: 100%; padding: 6px 8px; background: var(--bg-0); color: var(--fg-0); border: 1px solid var(--border); border-radius: 4px; font-size: 13px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.empty { font-size: 12px; color: var(--fg-1); padding: 8px 0; line-height: 1.6; }
.small { font-size: 11px; padding: 3px 8px; }
.danger { background: #5a2a2a; color: #ff8a80; border-color: #5a2a2a; }
.danger:hover { background: #6a3a3a; }
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--bg-3); color: var(--fg-0); padding: 6px 14px; border-radius: 4px; border: 1px solid var(--accent); z-index: 60; font-size: 13px; }
</style>
