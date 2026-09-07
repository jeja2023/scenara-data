<script setup lang="ts">
import { Activity, Database, RefreshCw, ServerCog, ShieldCheck } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

import { fetchHealth, fetchReadyz, loadConnection, type HealthResponse, type ReadyzResponse } from "../api";
import {
  formatTimestamp,
  labelHealthStatus,
  labelMaturity,
  labelPrincipalType,
  labelReadinessCheck,
  labelReadinessState,
  labelRuntimeMode,
} from "../labels";
import { useRefresh } from "../composables/useRefresh";
import UiTabs from "../components/UiTabs.vue";

const readyz = ref<ReadyzResponse | null>(null);
const health = ref<HealthResponse | null>(null);
const loading = ref(false);
const error = ref("");

const activeTab = ref<"readiness" | "runtime" | "session">("readiness");
const connection = ref(loadConnection());

const readinessLabel = computed(() => {
  if (readyz.value) {
    return labelReadinessState(readyz.value.status === "ready" ? "ready" : "not_ready");
  }
  return health.value ? labelReadinessState("not_ready") : labelReadinessState("offline");
});

const tabs = computed(() => [
  {
    id: "readiness",
    label: "依赖与基础设施就绪",
    icon: Activity,
    badge: Object.keys(readyz.value?.checks ?? {}).length
      ? `${Object.values(readyz.value?.checks ?? {}).filter(Boolean).length}/${Object.keys(readyz.value?.checks ?? {}).length}`
      : undefined,
  },
  {
    id: "runtime",
    label: "服务运行时状态",
    icon: ShieldCheck,
  },
  {
    id: "session",
    label: "连接与会话配置",
    icon: ServerCog,
  },
]);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  readyz.value = null;
  health.value = null;
  try {
    connection.value = loadConnection();
    const [readyResult, healthResult] = await Promise.allSettled([
      fetchReadyz(connection.value),
      fetchHealth(connection.value),
    ]);
    if (readyResult.status === "fulfilled") {
      readyz.value = readyResult.value;
    }
    if (healthResult.status === "fulfilled") {
      health.value = healthResult.value;
    }
    const errors: string[] = [];
    if (readyResult.status === "rejected") {
      errors.push(readyResult.reason instanceof Error ? readyResult.reason.message : "就绪探针失败");
    }
    if (healthResult.status === "rejected") {
      errors.push(healthResult.reason instanceof Error ? healthResult.reason.message : "健康探针失败");
    }
    if (errors.length) {
      error.value = errors.join("；");
    }
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
    <div class="hero-band panel" style="margin-bottom: 16px;">
      <div>
        <p class="eyebrow">scenara data · 运维与监控</p>
        <h2>运维探针与服务健康度</h2>
        <p class="hero-copy">
          实时监测数据平台后端进程、外部数据库存储中间件就绪状态，并审计当前浏览器会话凭证。
        </p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />{{ loading ? "正在探测..." : "执行探测" }}
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <!-- 顶部状态指示面板 -->
    <div class="stats-grid">
      <article class="stat-panel">
        <span>运行存储模式</span>
        <strong>{{ labelRuntimeMode(health?.runtime_mode) }}</strong>
        <small>{{ health?.version || "版本未知" }}</small>
      </article>
      <article class="stat-panel">
        <span>服务就绪状态</span>
        <strong>{{ readinessLabel }}</strong>
        <small>{{ readyz?.timestamp ? `检查时间：${formatTimestamp(readyz.timestamp)}` : "未检测" }}</small>
      </article>
      <article class="stat-panel">
        <span>API 服务端点</span>
        <strong class="truncate">{{ connection.apiBase || "同源直连服务" }}</strong>
        <small>{{ connection.tenantId }} / {{ connection.projectId }}</small>
      </article>
      <article class="stat-panel">
        <span>操作主体标识</span>
        <strong>{{ connection.principalId }}</strong>
        <small>{{ labelPrincipalType(connection.principalType) }}</small>
      </article>
    </div>

    <!-- 区域切换 Tab 按钮组 -->
    <UiTabs v-model="activeTab" :tabs="tabs" />

    <!-- Tab 1: 依赖与基础设施就绪 -->
    <div v-if="activeTab === 'readiness'" class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><Activity :size="18" /> 核心依赖就绪探测清单</h3>
          <span class="badge" :class="readyz?.status === 'ready' ? 'active' : 'paused'">
            {{ labelReadinessState(readyz?.status === 'ready' ? 'ready' : (readyz ? 'not_ready' : 'offline')) }}
          </span>
        </div>
        <div class="panel-body checklist">
          <div v-for="[key, ok] in Object.entries(readyz?.checks ?? {})" :key="key" class="check-row">
            <span>{{ labelReadinessCheck(key) }}</span>
            <span class="badge" :class="ok ? 'active' : 'draft'">
              {{ ok ? "探测正常 (通过)" : "未就绪 (失败)" }}
            </span>
          </div>
          <p class="muted tiny" style="margin: 8px 0 0;">
            {{ readyz?.timestamp ? `最近检查时间 (UTC+8)：${formatTimestamp(readyz.timestamp)}` : "点击右上角按钮执行探测" }}
          </p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Database :size="18" /> 安全与存储基础设施</h3>
          <span class="muted tiny">拓扑配置</span>
        </div>
        <div class="panel-body checklist">
          <div class="check-row">
            <span>持久化业务数据库 (Repository)</span>
            <strong class="mono">PostgreSQL</strong>
          </div>
          <div class="check-row">
            <span>分布式缓存与排队锁 (Lock & Cache)</span>
            <strong class="mono">Redis</strong>
          </div>
          <div class="check-row">
            <span>对象存储事实端点 (Object Storage)</span>
            <strong class="mono">MinIO / S3</strong>
          </div>
          <div class="check-row">
            <span>领域事件投递发件箱 (Domain Outbox)</span>
            <strong class="mono">Core Event Endpoint</strong>
          </div>
          <p class="muted tiny" style="margin: 8px 0 0;">
            展示服务层中间件治理拓扑，所有敏感密码与密钥均由服务端环境变量严格隔离。
          </p>
        </div>
      </section>
    </div>

    <!-- Tab 2: 服务运行时状态 -->
    <section v-if="activeTab === 'runtime'" class="panel">
      <div class="panel-header">
        <h3><ShieldCheck :size="18" /> 服务运行时规范与健康指标</h3>
      </div>
      <div class="panel-body kv-grid">
        <div>
          <span>服务名称</span>
          <strong class="mono">{{ health?.service || "scenara data" }}</strong>
        </div>
        <div>
          <span>规范成熟度</span>
          <strong>{{ labelMaturity(health?.maturity) }}</strong>
        </div>
        <div>
          <span>后端进程健康状态</span>
          <span class="badge" :class="health?.status === 'healthy' ? 'active' : 'draft'">
            {{ labelHealthStatus(health?.status) }}
          </span>
        </div>
        <div>
          <span>基础设施综合就绪</span>
          <span class="badge" :class="Object.values(readyz?.checks ?? {}).every(Boolean) ? 'active' : 'paused'">
            {{ Object.values(readyz?.checks ?? {}).every(Boolean) ? "全部通过" : "存在未通过项" }}
          </span>
        </div>
      </div>
    </section>

    <!-- Tab 3: 连接与会话配置 -->
    <section v-if="activeTab === 'session'" class="panel">
      <div class="panel-header">
        <h3><ServerCog :size="18" /> 当前会话连接与访问凭证摘要</h3>
      </div>
      <div class="panel-body">
        <dl class="kv-list">
          <div>
            <dt>服务连接目标 (API Endpoint)</dt>
            <dd class="mono">{{ connection.apiBase || "同源直连 (同端口反向代理)" }}</dd>
          </div>
          <div>
            <dt>会话归属组织与项目</dt>
            <dd class="mono">{{ connection.tenantId }} / {{ connection.projectId }}</dd>
          </div>
          <div class="span-2">
            <dt>会话权限范围 (Permission Scopes)</dt>
            <dd class="mono tiny" style="word-break: break-all;">
              {{ connection.scopes || "暂无权限范围声明" }}
            </dd>
          </div>
          <div class="span-2">
            <dt>已授权产品权益 (Product Entitlements)</dt>
            <dd class="mono tiny">
              {{ connection.entitlements || "暂无产品权益声明" }}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  </section>
</template>
