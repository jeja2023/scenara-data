<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Activity, Database, Layers3, RefreshCw } from "@lucide/vue";

import { fetchHealth, fetchReadyz, listDatasetVersions, listDatasets } from "../api";
import {
  formatNumber,
  formatTimestamp,
  labelDatasetVersionStatus,
  labelDatasetStatus,
  labelReadinessCheck,
  labelReadinessState,
} from "../labels";
import type { DatasetRecord, DatasetVersion, Page, ReadyzResponse } from "../types";
import { useRefresh } from "../composables/useRefresh";

const readyz = ref<ReadyzResponse | null>(null);
const readinessState = ref<"ready" | "not_ready" | "offline">("offline");
const datasets = ref<DatasetRecord[]>([]);
const publishedVersions = ref<DatasetVersion[]>([]);
const loading = ref(false);
const error = ref("");

const readyChecks = computed(() => Object.entries(readyz.value?.checks ?? {}));

const stats = computed(() => [
  { label: "数据集", value: datasets.value.length, hint: "当前租户与项目" },
  {
    label: "已发布版本",
    value: publishedVersions.value.length,
    hint: "生产可用的不可变版本",
  },
  {
    label: "后端状态",
    value: labelReadinessState(readinessState.value),
    hint: readyz.value?.timestamp ? formatTimestamp(readyz.value.timestamp) : "尚未刷新",
  },
  {
    label: "依赖检查",
    value: readyChecks.value.filter(([, ok]) => ok).length,
    hint: `${readyChecks.value.length} 项可用`,
  },
]);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  datasets.value = [];
  publishedVersions.value = [];
  readyz.value = null;
  readinessState.value = "offline";
  try {
    const errors: string[] = [];
    let nextReadyz: ReadyzResponse | null = null;
    let nextState: "ready" | "not_ready" | "offline" = "offline";
    const [readyResult, healthResult, datasetResult] = await Promise.allSettled([
      fetchReadyz(),
      fetchHealth(),
      listDatasets(),
    ]);
    if (readyResult.status === "fulfilled") {
      nextReadyz = readyResult.value;
      nextState = readyResult.value.status === "ready" ? "ready" : "not_ready";
    } else {
      errors.push(readyResult.reason instanceof Error ? readyResult.reason.message : "就绪探针失败");
    }
    if (healthResult.status === "fulfilled" && !nextReadyz) {
      nextReadyz = {
        status: "not_ready",
        service: healthResult.value.service,
        runtime_mode: healthResult.value.runtime_mode,
        checks: {},
        timestamp: healthResult.value.timestamp,
      };
      nextState = "not_ready";
    } else if (healthResult.status === "rejected" && !nextReadyz) {
      nextState = "offline";
      errors.push(healthResult.reason instanceof Error ? healthResult.reason.message : "健康探针失败");
    }
    if (datasetResult.status === "fulfilled") {
      datasets.value = datasetResult.value.items;
    } else {
      errors.push(datasetResult.reason instanceof Error ? datasetResult.reason.message : "数据集加载失败");
    }
    const versionPages = await Promise.all(
      datasets.value.slice(0, 8).map((dataset) =>
        listDatasetVersions(dataset.dataset_id).catch(() => ({
          items: [],
          total: 0,
          next_cursor: null,
        }) as Page<DatasetVersion>),
      ),
    );
    publishedVersions.value = versionPages
      .flatMap((page) => page.items)
      .filter((item) => item.status === "published")
      .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))
      .slice(0, 12);
    readyz.value = nextReadyz;
    readinessState.value = nextState;
    if (errors.length) {
      error.value = errors.join("；");
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "总览加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
useRefresh(refresh);
</script>

<template>
  <section class="page overview-page">
    <div class="hero-band panel">
      <div>
        <p class="eyebrow">景枢数据 · 统一门户接入</p>
        <h2>数据管理工作台</h2>
        <p class="hero-copy">
          以统一主题、统一身份和独立部署前端呈现数据资产、数据集、版本、难例和运维状态。
        </p>
      </div>
      <button class="button secondary" @click="refresh">
        <RefreshCw :size="16" />刷新
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <div class="stats-grid">
      <article v-for="item in stats" :key="item.label" class="stat-panel">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </div>

    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3><Database :size="18" />最近数据集</h3>
          <span class="muted">{{ formatNumber(datasets.length) }} 个</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>状态</th>
                <th>说明</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="dataset in datasets.slice(0, 8)" :key="dataset.dataset_id">
                <td>
                  <strong>{{ dataset.name }}</strong>
                  <div class="muted mono">{{ dataset.dataset_id }}</div>
                </td>
                <td>
                  <span class="badge" :class="dataset.status">{{ labelDatasetStatus(dataset.status) }}</span>
                </td>
                <td class="truncate">{{ dataset.description || "-" }}</td>
                <td>{{ formatTimestamp(dataset.updated_at) }}</td>
              </tr>
              <tr v-if="!datasets.length">
                <td colspan="4" class="empty">暂无数据集</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3><Activity :size="18" />就绪检查</h3>
          <span class="badge" :class="readyz?.status === 'ready' ? 'active' : 'paused'">
            {{ labelReadinessState(readyz?.status === 'ready' ? 'ready' : (readyz ? 'not_ready' : 'offline')) }}
          </span>
        </div>
        <div class="panel-body checklist">
          <div v-for="[key, ok] in readyChecks" :key="key" class="check-row">
            <span>{{ labelReadinessCheck(key) }}</span>
            <strong :class="ok ? 'ok' : 'warn'">{{ ok ? '通过' : '失败' }}</strong>
          </div>
          <p class="muted tiny">{{ readyz?.timestamp ? `最近检查：${formatTimestamp(readyz.timestamp)}` : '尚未执行检查' }}</p>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-header">
        <h3><Layers3 :size="18" />最近已发布版本</h3>
        <span class="muted">{{ publishedVersions.length }} 条</span>
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>数据集</th>
              <th>版本</th>
              <th>状态</th>
              <th>摘要</th>
              <th>发布时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="version in publishedVersions" :key="version.dataset_version_id">
              <td>{{ version.dataset_id }}</td>
              <td>{{ version.version }}</td>
              <td><span class="badge active">{{ labelDatasetVersionStatus(version.status) }}</span></td>
              <td class="mono truncate">{{ version.manifest_sha256 || '-' }}</td>
              <td>{{ formatTimestamp(version.published_at || version.created_at) }}</td>
            </tr>
            <tr v-if="!publishedVersions.length">
              <td colspan="5" class="empty">暂无已发布版本</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
