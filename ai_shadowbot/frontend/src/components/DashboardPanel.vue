<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total_runs }}</div>
        <div class="stat-label">总执行数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" :class="stats.success_rate >= 80 ? 'good' : stats.success_rate >= 50 ? 'warn' : 'bad'">{{ stats.success_rate }}%</div>
        <div class="stat-label">成功率</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.avg_duration }}s</div>
        <div class="stat-label">平均耗时</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.today_runs }}</div>
        <div class="stat-label">今日执行</div>
      </div>
    </div>

    <!-- 7天趋势 -->
    <h4 class="section-title">近 7 天执行趋势</h4>
    <div v-if="trend.length" class="trend-bars">
      <div v-for="d in trend" :key="d.date" class="trend-bar-wrap">
        <div class="trend-bar" :style="{ height: barHeight(d.count) + 'px' }" :title="`${d.date}: ${d.count} 次`"></div>
        <div class="trend-label">{{ d.date.slice(5) }}</div>
      </div>
    </div>
    <div v-else class="empty">暂无数据</div>

    <!-- 最近执行 -->
    <h4 class="section-title">最近执行</h4>
    <div v-if="recent.length" class="recent-list">
      <div v-for="r in recent" :key="r.run_id" class="recent-row">
        <span :class="['status', r.status]">{{ badge(r.status) }}</span>
        <span class="wf-name">{{ r.workflow_name || r.workflow_id }}</span>
        <span class="mode">{{ r.mode === 'real' ? '真实' : '演练' }}</span>
        <span class="time">{{ fmtTime(r.started_at) }}</span>
        <span class="dur">{{ r.duration ? r.duration.toFixed(1) + 's' : '-' }}</span>
      </div>
    </div>
    <div v-else class="empty">尚无执行记录</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type RunSummary, type WorkflowSummary } from '../api-service'

const stats = ref({ total_runs: 0, success_rate: 0, avg_duration: 0, today_runs: 0 })
const trend = ref<{ date: string; count: number }[]>([])
const recent = ref<(RunSummary & { workflow_name?: string })[]>([])

const MAX_BAR = 120

function barHeight(c: number) {
  const maxC = Math.max(...trend.value.map(d => d.count), 1)
  return Math.max(4, Math.round((c / maxC) * MAX_BAR))
}

function badge(s: string) {
  return s === 'success' ? '✓' : s === 'failed' ? '✗' : s === 'running' ? '●' : '○'
}

function fmtTime(t?: string) {
  if (!t) return '-'
  return t.slice(5, 16).replace('T', ' ')
}

onMounted(async () => {
  try {
    const all: { runs: RunSummary[]; name: string }[] = []
    const wfs: WorkflowSummary[] = await api.listWorkflows()
    for (const wf of wfs) {
      try {
        const runs = await api.getRunsExtended(wf.id)
        all.push({ runs: runs || [], name: wf.name })
      } catch { /* skip */ }
    }

    const flat = all.flatMap(a => a.runs.map(r => ({ ...r, workflow_name: a.name })))
    if (!flat.length) return

    const success = flat.filter(r => r.status === 'success').length
    const total = flat.length
    const totalDur = flat.reduce((s, r) => s + (r.duration || 0), 0)
    const today = new Date().toISOString().slice(0, 10)
    const todayCount = flat.filter(r => (r.started_at || '').startsWith(today)).length

    stats.value = {
      total_runs: total,
      success_rate: total ? Math.round((success / total) * 100) : 0,
      avg_duration: total ? +(totalDur / total / 1000).toFixed(1) : 0,
      today_runs: todayCount,
    }

    // 7天趋势
    const days: Record<string, number> = {}
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10)
      days[d] = 0
    }
    for (const r of flat) {
      const d = (r.started_at || '').slice(0, 10)
      if (d in days) days[d]++
    }
    trend.value = Object.entries(days).map(([date, count]) => ({ date, count }))

    // 最近10条
    recent.value = flat
      .sort((a, b) => (b.started_at || '').localeCompare(a.started_at || ''))
      .slice(0, 10)
  } catch { /* ignore */ }
})
</script>

<style scoped>
.dashboard { padding: 4px 0; }
.stats-row { display: flex; gap: 8px; margin-bottom: 12px; }
.stat-card {
  flex: 1; background: var(--bg-2); border-radius: 6px;
  padding: 10px 8px; text-align: center;
}
.stat-num { font-size: 20px; font-weight: 700; color: var(--fg-0); }
.stat-num.good { color: var(--success); }
.stat-num.warn { color: #f0a000; }
.stat-num.bad { color: var(--failed); }
.stat-label { font-size: 11px; color: var(--fg-1); margin-top: 2px; }
.section-title { font-size: 12px; color: var(--fg-1); margin: 10px 0 6px; text-transform: uppercase; }
.trend-bars { display: flex; align-items: flex-end; gap: 6px; height: 140px; padding: 0 4px; }
.trend-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; }
.trend-bar {
  width: 28px; background: var(--accent); border-radius: 3px 3px 0 0;
  min-height: 4px; transition: height 0.3s;
}
.trend-label { font-size: 10px; color: var(--fg-1); margin-top: 4px; }
.recent-list { font-size: 12px; }
.recent-row { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: 3px; }
.recent-row:nth-child(odd) { background: rgba(128,128,128,0.05); }
.status { font-weight: bold; width: 16px; text-align: center; }
.status.success { color: var(--success); }
.status.failed { color: var(--failed); }
.wf-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mode { font-size: 11px; color: var(--fg-1); background: var(--bg-2); padding: 1px 4px; border-radius: 3px; }
.time { color: var(--fg-1); }
.dur { color: var(--fg-1); text-align: right; min-width: 36px; }
.empty { font-size: 12px; color: var(--fg-1); padding: 8px 0; }
</style>
