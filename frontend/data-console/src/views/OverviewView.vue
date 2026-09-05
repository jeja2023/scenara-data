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
  shortHash,
} from "../labels";
import type { DatasetRecord, DatasetVersion, Page, ReadyzResponse } from "../types";
import { useRefresh } from "../composables/useRefresh";
import UiTabs from "../components/UiTabs.vue";
import UiPagination from "../components/UiPagination.vue";
import UiSearchBox from "../components/UiSearchBox.vue";
import { usePagination } from "../composables/usePagination";

const readyz = ref<ReadyzResponse | null>(null);
const readinessState = ref<"ready" | "not_ready" | "offline">("offline");
const datasets = ref<DatasetRecord[]>([]);
const publishedVersions = ref<DatasetVersion[]>([]);
const loading = ref(false);
const error = ref("");

const activeTab = ref<"datasets" | "versions" | "readiness">("datasets");
const datasetSearch = ref("");
const versionSearch = ref("");

const readyChecks = computed(() => Object.entries(readyz.value?.checks ?? {}));
const readyCheckPassedCount = computed(() => readyChecks.value.filter(([, ok]) => ok).length);

const filteredDatasets = computed(() => {
  const q = datasetSearch.value.trim().toLowerCase();
  if (!q) return datasets.value;
  return datasets.value.filter(
    (d) =>
      d.name.toLowerCase().includes(q) ||
      d.dataset_id.toLowerCase().includes(q) ||
      (d.description && d.description.toLowerCase().includes(q)),
  );
});

const filteredVersions = computed(() => {
  const q = versionSearch.value.trim().toLowerCase();
  if (!q) return publishedVersions.value;
  return publishedVersions.value.filter(
    (v) =>
      v.dataset_id.toLowerCase().includes(q) ||
      v.version.toLowerCase().includes(q) ||
      (v.manifest_sha256 && v.manifest_sha256.toLowerCase().includes(q)),
  );
});

const datasetPagination = usePagination(filteredDatasets, 10);
const versionPagination = usePagination(filteredVersions, 10);

const tabs = computed(() => [
  {
    id: "datasets",
    label: "数据集概览",
    icon: Database,
    badge: datasets.value.length,
  },
  {
    id: "versions",
    label: "已发布版本",
    icon: Layers3,
    badge: publishedVersions.value.length,
  },
  {
    id: "readiness",
    label: "依赖就绪检查",
    icon: Activity,
    badge: `${readyCheckPassedCount.value}/${readyChecks.value.length || 0}`,
  },
]);

const stats = computed(() => [
  { label: "数据集总数", value: datasets.value.length, hint: "当前租户与项目下有效资产" },
  {
    label: "已发布版本",
    value: publishedVersions.value.length,
    hint: "生产可用的不可变训练版本",
  },
  {
    label: "后端运行状态",
    value: labelReadinessState(readinessState.value),
    hint: readyz.value?.timestamp ? formatTimestamp(readyz.value.timestamp) : "尚未刷新检测",
  },
  {
    label: "服务依赖探测",
    value: readyCheckPassedCount.value,
    hint: `共 ${readyChecks.value.length} 项基础设施可用`,
  },
]);

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
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
      datasets.value.slice(0, 10).map((dataset) =>
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
      .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)));
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
        <p class="eyebrow">景枢视觉 AI 平台 · 数据管理工作台</p>
        <h2>数据中枢控制台</h2>
        <p class="hero-copy">
          统一呈现数据资产生命周期、语义版本发布状态、难例纠正闭环以及基础设施就绪探针。
        </p>
      </div>
      <button class="button secondary" :disabled="loading" @click="refresh">
        <RefreshCw :size="16" />{{ loading ? "正在刷新..." : "刷新数据" }}
      </button>
    </div>

    <p v-if="error" class="callout error">{{ error }}</p>

    <!-- 核心统计面板 -->
    <div class="stats-grid">
      <article v-for="item in stats" :key="item.label" class="stat-panel">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </div>

    <!-- 区域切换 Tab 按钮组 -->
    <UiTabs v-model="activeTab" :tabs="tabs" />

    <!-- Tab 1: 最近数据集 -->
    <section v-if="activeTab === 'datasets'" class="panel">
      <div class="panel-header">
        <h3><Database :size="18" /> 数据集资产列表</h3>
        <UiSearchBox v-model="datasetSearch" placeholder="搜索数据集名称或 ID..." />
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 240px;" />
            <col style="width: 120px;" />
            <col />
            <col style="width: 190px;" />
          </colgroup>
          <thead>
            <tr>
              <th>名称 / 标识</th>
              <th>运行状态</th>
              <th>描述说明</th>
              <th>最后更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="dataset in datasetPagination.paginatedItems.value" :key="dataset.dataset_id">
              <td>
                <span class="cell-ellipsis" v-tooltip="`${dataset.name} (${dataset.dataset_id})`">
                  <strong>{{ dataset.name }}</strong>
                  <span class="muted mono"> · {{ dataset.dataset_id }}</span>
                </span>
              </td>
              <td>
                <span class="badge" :class="dataset.status">{{ labelDatasetStatus(dataset.status) }}</span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="dataset.description || '暂无描述说明'">
                  {{ dataset.description || "-" }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="formatTimestamp(dataset.updated_at)">
                  {{ formatTimestamp(dataset.updated_at) }}
                </span>
              </td>
            </tr>
            <tr v-if="!datasetPagination.paginatedItems.value.length">
              <td colspan="4" class="empty">暂无匹配的数据集资产</td>
            </tr>
          </tbody>
        </table>
      </div>
      <UiPagination
        v-model:page="datasetPagination.page.value"
        v-model:page-size="datasetPagination.pageSize.value"
        :total="datasetPagination.total.value"
      />
    </section>

    <!-- Tab 2: 已发布版本 -->
    <section v-if="activeTab === 'versions'" class="panel">
      <div class="panel-header">
        <h3><Layers3 :size="18" /> 已发布生产版本列表</h3>
        <UiSearchBox v-model="versionSearch" placeholder="搜索所属数据集或版本号..." />
      </div>
      <div class="table-scroll">
        <table class="data-table">
          <colgroup>
            <col style="width: 200px;" />
            <col style="width: 120px;" />
            <col style="width: 100px;" />
            <col style="width: 220px;" />
            <col style="width: 190px;" />
          </colgroup>
          <thead>
            <tr>
              <th>所属数据集</th>
              <th>语义版本</th>
              <th>状态</th>
              <th>清单摘要校验和</th>
              <th>发布时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="version in versionPagination.paginatedItems.value" :key="version.dataset_version_id">
              <td>
                <span class="cell-ellipsis mono" v-tooltip="version.dataset_id">
                  {{ version.dataset_id }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="version.version">
                  <strong>{{ version.version }}</strong>
                </span>
              </td>
              <td>
                <span class="badge active">{{ labelDatasetVersionStatus(version.status) }}</span>
              </td>
              <td>
                <span class="cell-ellipsis mono" v-tooltip="version.manifest_sha256 || '-'">
                  {{ shortHash(version.manifest_sha256 || "") }}
                </span>
              </td>
              <td>
                <span class="cell-ellipsis" v-tooltip="formatTimestamp(version.published_at || version.created_at)">
                  {{ formatTimestamp(version.published_at || version.created_at) }}
                </span>
              </td>
            </tr>
            <tr v-if="!versionPagination.paginatedItems.value.length">
              <td colspan="5" class="empty">暂无已发布生产版本</td>
            </tr>
          </tbody>
        </table>
      </div>
      <UiPagination
        v-model:page="versionPagination.page.value"
        v-model:page-size="versionPagination.pageSize.value"
        :total="versionPagination.total.value"
      />
    </section>

    <!-- Tab 3: 系统就绪检查 -->
    <section v-if="activeTab === 'readiness'" class="panel">
      <div class="panel-header">
        <h3><Activity :size="18" /> 核心基础设施与服务探测</h3>
        <span class="badge" :class="readyz?.status === 'ready' ? 'active' : 'paused'">
          {{ labelReadinessState(readyz?.status === 'ready' ? 'ready' : (readyz ? 'not_ready' : 'offline')) }}
        </span>
      </div>
      <div class="panel-body checklist">
        <div v-for="[key, ok] in readyChecks" :key="key" class="check-row">
          <span>{{ labelReadinessCheck(key) }}</span>
          <strong :class="ok ? 'ok' : 'warn'">{{ ok ? "探测正常 (通过)" : "探测异常 (失败)" }}</strong>
        </div>
        <p class="muted tiny" style="margin-top: 10px;">
          {{ readyz?.timestamp ? `最近探测时间：${formatTimestamp(readyz.timestamp)}` : "尚未执行检查" }}
        </p>
      </div>
    </section>
  </section>
</template>
