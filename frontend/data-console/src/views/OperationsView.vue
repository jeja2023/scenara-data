<script setup lang="ts">
import { Activity, Database, RefreshCw, ServerCog, ShieldCheck } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

import { fetchHealth, fetchReadyz, loadConnection, type HealthResponse, type ReadyzResponse } from "../api";
import { formatTimestamp } from "../labels";
import { useRefresh } from "../composables/useRefresh";

const readyz = ref<ReadyzResponse | null>(null);
const health = ref<HealthResponse | null>(null);
const loading = ref(false);
const error = ref("");

const connection = computed(() => loadConnection());

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    readyz.value = await fetchReadyz();
    health.value = await fetchHealth();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "运维探针加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page operations-page">
    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="stats-grid">
      <article class="stat-panel">
        <span>运行模式</span>
        <strong>{{ health?.runtime_mode || '未知' }}</strong>
        <small>{{ health?.version || '暂无版本' }}</small>
      </article>
      <article class="stat-panel">
        <span>就绪状态</span>
        <strong>{{ readyz?.status === 'ready' ? '已就绪' : readyz ? '未就绪' : '待检查' }}</strong>
        <small>{{ readyz?.timestamp ? formatTimestamp(readyz.timestamp) : '未检测' }}</small>
      </article>
      <article class="stat-panel">
        <span>API 地址</span>
        <strong class="truncate">{{ connection.apiBase || 'same-origin' }}</strong>
        <small>{{ connection.tenantId }}/{{ connection.projectId }}</small>
      </article>
      <article class="stat-panel">
        <span>主体</span>
        <strong>{{ connection.principalId }}</strong>
        <small>{{ connection.principalType }}</small>
      </article>
    </div>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><Activity :size="18" /> 依赖就绪</h3>
          <button class="button secondary" @click="refresh"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="panel-body checklist">
          <div v-for="[key, ok] in Object.entries(readyz?.checks ?? {})" :key="key" class="check-row">
            <span>{{ key }}</span>
            <strong :class="ok ? 'ok' : 'warn'">{{ ok ? '通过' : '失败' }}</strong>
          </div>
          <p class="muted tiny">{{ readyz?.timestamp ? `最近检查：${formatTimestamp(readyz.timestamp)}` : '点击刷新执行探测' }}</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Database :size="18" /> 安全与存储</h3>
        </div>
        <div class="panel-body checklist">
          <div class="check-row"><span>数据源</span><strong>PostgreSQL</strong></div>
          <div class="check-row"><span>缓存与锁</span><strong>Redis</strong></div>
          <div class="check-row"><span>对象存储</span><strong>MinIO / S3</strong></div>
          <div class="check-row"><span>事件回传</span><strong>Core Event Endpoint</strong></div>
          <p class="muted tiny">当前只展示本地开发和治理信息，不包含业务数据。</p>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-header">
        <h3><ShieldCheck :size="18" /> 运行信息</h3>
      </div>
      <div class="panel-body kv-grid">
        <div><span>服务</span><strong>{{ health?.service || 'scenara-data' }}</strong></div>
        <div><span>成熟度</span><strong>{{ health?.maturity || 'implemented' }}</strong></div>
        <div><span>后端状态</span><strong>{{ health?.status || 'unknown' }}</strong></div>
        <div><span>检查结果</span><strong>{{ Object.values(readyz?.checks ?? {}).every(Boolean) ? '全部通过' : '存在失败' }}</strong></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3><ServerCog :size="18" /> 配置摘要</h3>
      </div>
      <div class="panel-body">
        <p class="muted">连接目标：<span class="mono">{{ connection.apiBase || 'same-origin' }}</span></p>
        <p class="muted">权限范围：<span class="mono truncate">{{ connection.scopes }}</span></p>
        <p class="muted">产品授权：<span class="mono">{{ connection.entitlements }}</span></p>
      </div>
    </section>
  </section>
</template>

