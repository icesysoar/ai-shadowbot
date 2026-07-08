<template>
  <div class="template-panel">
    <h3>模板</h3>

    <!-- 搜索与筛选 -->
    <div class="search-bar">
      <input
        v-model="searchQuery"
        placeholder="搜索模板..."
        @keyup.enter="fetchTemplates"
      />
      <select v-model="categoryFilter" @change="fetchTemplates">
        <option value="">全部分类</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
    </div>

    <!-- 模板列表 -->
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="error" class="err-msg">{{ error }}</div>
    <div v-else-if="!templates.length" class="empty">暂无模板</div>
    <div v-else class="template-list">
      <div
        v-for="t in templates"
        :key="t.id"
        :class="['template-card', { expanded: expandedId === t.id }]"
      >
        <div class="card-main" @click="toggleExpand(t.id)">
          <div class="card-head">
            <span class="card-name">{{ t.name }}</span>
            <span class="card-cat">{{ t.category }}</span>
          </div>
          <div class="card-meta">
            <span v-if="t.tags?.length" class="tags">
              <span v-for="tag in t.tags" :key="tag" class="tag">{{ tag }}</span>
            </span>
            <span class="usage">使用 {{ t.usage_count }} 次</span>
          </div>
        </div>

        <!-- 展开详情 -->
        <div v-if="expandedId === t.id" class="card-detail">
          <div v-if="loadingDetail && loadingId === t.id" class="empty">加载中...</div>
          <div v-else-if="templateDetail && templateDetail.id === t.id">
            <p v-if="templateDetail.description" class="tpl-desc">
              {{ templateDetail.description }}
            </p>
            <div class="tpl-stats">
              节点 {{ templateDetail.flow?.nodes?.length || 0 }}
              · 连线 {{ templateDetail.flow?.edges?.length || 0 }}
            </div>
            <button class="btn-primary" @click.stop="useTemplate(t.id)">
              使用此模板
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 另存为模板 -->
    <div v-if="hasWorkflow" class="save-section">
      <h4>当前工作流</h4>
      <button class="btn-sm" @click="showSaveForm = !showSaveForm">
        {{ showSaveForm ? '取消' : '另存为模板' }}
      </button>
      <div v-if="showSaveForm" class="save-form">
        <div class="field">
          <label>名称</label>
          <input v-model="saveForm.name" placeholder="模板名称" />
        </div>
        <div class="field">
          <label>分类</label>
          <input v-model="saveForm.category" placeholder="如：自动化、办公" />
        </div>
        <div class="field">
          <label>描述</label>
          <input v-model="saveForm.description" placeholder="简要描述" />
        </div>
        <button
          class="btn-primary"
          :disabled="!saveForm.name.trim()"
          @click="doSaveTemplate"
        >
          保存
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type TemplateSummary, type TemplateDetail } from '../api-service'

const props = defineProps<{
  currentWorkflowId?: string | null
}>()

const emit = defineEmits<{
  (e: 'use-template', templateId: string): void
}>()

const templates = ref<TemplateSummary[]>([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')
const categoryFilter = ref('')
const categories = ref<string[]>([])
const expandedId = ref<string | null>(null)
const templateDetail = ref<TemplateDetail | null>(null)
const loadingDetail = ref(false)
const loadingId = ref<string | null>(null)
const showSaveForm = ref(false)
const saveForm = ref({ name: '', category: '', description: '' })

const hasWorkflow = computed(() => !!props.currentWorkflowId)

async function fetchTemplates() {
  loading.value = true
  error.value = ''
  try {
    const params: { category?: string; search?: string } = {}
    if (categoryFilter.value) params.category = categoryFilter.value
    if (searchQuery.value.trim()) params.search = searchQuery.value.trim()
    const list = await api.listTemplates(params)
    templates.value = list
    // 收集分类
    const catSet = new Set(list.map(t => t.category).filter(Boolean))
    categories.value = Array.from(catSet).sort()
  } catch (e: any) {
    error.value = '加载失败：' + e.message
  } finally {
    loading.value = false
  }
}

async function toggleExpand(id: string) {
  if (expandedId.value === id) {
    expandedId.value = null
    return
  }
  expandedId.value = id
  loadingDetail.value = true
  loadingId.value = id
  try {
    templateDetail.value = await api.getTemplate(id)
  } catch (e: any) {
    error.value = '加载模板详情失败：' + e.message
  } finally {
    loadingDetail.value = false
    loadingId.value = null
  }
}

async function useTemplate(id: string) {
  emit('use-template', id)
}

async function doSaveTemplate() {
  if (!props.currentWorkflowId || !saveForm.value.name.trim()) return
  try {
    await api.saveAsTemplate(props.currentWorkflowId, {
      name: saveForm.value.name.trim(),
      category: saveForm.value.category.trim() || undefined,
      description: saveForm.value.description.trim() || undefined,
    })
    showSaveForm.value = false
    saveForm.value = { name: '', category: '', description: '' }
    await fetchTemplates()
  } catch (e: any) {
    error.value = '保存模板失败：' + e.message
  }
}

onMounted(fetchTemplates)
</script>

<style scoped>
.template-panel {
  font-size: 12px;
}
.template-panel h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.template-panel h4 {
  margin: 10px 0 6px;
  font-size: 12px;
  color: var(--fg-1);
}

.search-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}
.search-bar input {
  flex: 1;
  font-size: 12px;
  padding: 4px 8px;
}
.search-bar select {
  font-size: 12px;
  padding: 4px 6px;
  max-width: 100px;
}

.template-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 8px;
}
.template-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.card-main {
  padding: 8px 10px;
  cursor: pointer;
}
.card-main:hover {
  background: rgba(74, 158, 255, 0.05);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.card-name {
  font-weight: 600;
}
.card-cat {
  font-size: 10px;
  background: var(--accent);
  color: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}
.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--fg-1);
}
.tags {
  display: flex;
  gap: 3px;
}
.tag {
  background: var(--bg-0);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
}
.usage {
  font-family: monospace;
  color: var(--accent-2);
}

.card-detail {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  background: rgba(0,0,0,0.1);
}
.tpl-desc {
  margin: 0 0 6px;
  color: var(--fg-1);
}
.tpl-stats {
  font-size: 11px;
  color: var(--accent-2);
  margin-bottom: 6px;
}

.save-section {
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
.save-form {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  margin-top: 8px;
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
  font-size: 12px;
  padding: 4px 8px;
}

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
