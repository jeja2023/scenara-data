<script setup lang="ts">
import {
  Activity,
  Database,
  FlaskConical,
  Layers3,
  Menu,
  RefreshCw,
  Settings2,
  X,
} from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import { fetchHealth, fetchReadyz, loadConnection, saveConnection, type ConnectionSettings } from "./api";
import { REFRESH_EVENT } from "./composables/useRefresh";
import { labelPrincipalType, labelReadinessState } from "./labels";
import { routes } from "./router";

type NavRoute = {
  path: string;
  meta?: {
    section?: string;
    title?: string;
    description?: string;
    icon?: unknown;
    platform?: string;
    hideFromNavigation?: boolean;
  };
};

const route = useRoute();
const navOpen = ref(false);
const settingsOpen = ref(false);
const readyState = ref<"checking" | "ready" | "offline" | "not_ready">("checking");
const readyChecks = ref<Record<string, boolean>>({});
const readyMessage = ref("正在检查后端状态");
const connection = ref<ConnectionSettings>(loadConnection());
const draft = reactive<ConnectionSettings>(loadConnection());
let refreshTimer: number | null = null;

const navSections = computed(() => {
  const sections = new Map<string, NavRoute[]>();
  for (const item of routes as unknown as NavRoute[]) {
    if (item.meta?.hideFromNavigation) continue;
    const section = String(item.meta?.section ?? "其他");
    sections.set(section, [...(sections.get(section) ?? []), item]);
  }
  return sections;
});

const routeMeta = computed(
  () => route.meta as { title?: string; description?: string; platform?: string },
);

const pageTitle = computed(() => String(routeMeta.value.title ?? "景枢数据"));
const pageDescription = computed(() => String(routeMeta.value.description ?? ""));

const platform = computed(() => String(routeMeta.value.platform ?? "data"));

function openSettings(): void {
  Object.assign(draft, loadConnection());
  settingsOpen.value = true;
  void nextTick(() => document.querySelector<HTMLInputElement>("#api-base")?.focus());
}

function applySettings(): void {
  const next = { ...draft, apiBase: draft.apiBase.replace(/\/$/, "") };
  saveConnection(next);
  connection.value = next;
  settingsOpen.value = false;
  window.dispatchEvent(new CustomEvent(REFRESH_EVENT));
  void probeConnection(next);
}

function triggerRefresh(): void {
  window.dispatchEvent(new CustomEvent(REFRESH_EVENT));
  void checkReadyz();
}

async function probeConnection(source: ConnectionSettings): Promise<void> {
  readyState.value = "checking";
  const [probeResult, healthResult] = await Promise.allSettled([
    fetchReadyz(source),
    fetchHealth(source),
  ]);
  if (probeResult.status === "fulfilled") {
    readyChecks.value = probeResult.value.checks;
    readyState.value = probeResult.value.status === "ready" ? "ready" : "not_ready";
  } else {
    readyChecks.value = {};
    readyState.value = healthResult.status === "fulfilled" ? "not_ready" : "offline";
  }
  if (healthResult.status === "fulfilled") {
    readyMessage.value = healthResult.value.status === "ok" ? "后端可访问" : "后端依赖未完全就绪";
  } else if (probeResult.status === "fulfilled") {
    readyMessage.value = "就绪探针可用，健康探针未响应";
  } else {
    readyMessage.value = "无法连接到后端";
  }
}

function checkReadyz(): void {
  void probeConnection(connection.value);
}

function testConnection(): void {
  void probeConnection({ ...draft, apiBase: draft.apiBase.replace(/\/$/, "") });
}

function closeNav(): void {
  navOpen.value = false;
}

onMounted(() => {
  void checkReadyz();
  refreshTimer = window.setInterval(checkReadyz, 15000);
});

onBeforeUnmount(() => {
  if (refreshTimer !== null) window.clearInterval(refreshTimer);
});

watch(
  () => route.fullPath,
  () => {
    navOpen.value = false;
  },
);
</script>

<template>
  <div class="shell" :data-platform="platform">
    <a class="skip-link" href="#main-content">跳到主内容</a>

    <header class="topbar">
      <button class="icon-button mobile-menu" title="打开导航" @click="navOpen = true">
        <Menu :size="18" />
      </button>

      <div class="brand-lockup">
        <div class="brand-mark">数</div>
        <div>
          <strong>景枢数据</strong>
          <span>{{ connection.apiBase || '本地连接' }}</span>
        </div>
      </div>

      <div class="topbar-context">
        <span class="context-product">统一门户 · 独立前端</span>
        <span class="context-separator"></span>
        <h1 class="context-title">{{ pageTitle }}</h1>
        <span v-if="pageDescription" class="context-description">{{ pageDescription }}</span>
      </div>

      <div class="topbar-actions">
        <button class="icon-button" title="刷新" @click="triggerRefresh">
          <RefreshCw :size="18" />
        </button>
        <button class="connection" :class="readyState" :title="labelReadinessState(readyState)" @click="checkReadyz">
          <span></span>{{ labelReadinessState(readyState) }}
        </button>
        <button class="icon-button" title="连接设置" @click="openSettings">
          <Settings2 :size="18" />
        </button>
      </div>
    </header>

    <aside class="sidebar" :class="{ open: navOpen }">
      <div class="sidebar-brand">
        <div class="brand-mark large">数</div>
        <div>
          <strong>景枢数据</strong>
          <span>{{ connection.tenantId }}/{{ connection.projectId }}</span>
        </div>
        <button class="icon-button sidebar-close" title="关闭导航" @click="closeNav">
          <X :size="18" />
        </button>
      </div>

      <nav aria-label="主导航">
        <section v-for="[section, items] in navSections" :key="section">
          <p>{{ section }}</p>
          <RouterLink
            v-for="item in items"
            :key="item.path"
            :to="item.path"
            class="nav-link"
          >
            <component :is="item.meta?.icon" :size="17" />
            <span>{{ item.meta?.title }}</span>
          </RouterLink>
        </section>
      </nav>

      <div class="sidebar-footer">
        <span>v0.1.4</span><i></i><span>{{ readyMessage }}</span>
      </div>
    </aside>

    <button v-if="navOpen" class="nav-scrim" aria-label="关闭导航" @click="closeNav"></button>

    <main id="main-content" class="main-content" tabindex="-1">
      <RouterView />
    </main>

    <dialog :open="settingsOpen" class="modal" @close="settingsOpen = false">
      <form method="dialog" @submit.prevent="applySettings">
        <div class="modal-header">
          <div>
            <h2>连接设置</h2>
            <p>本地浏览器会话</p>
          </div>
          <button class="icon-button" type="button" title="关闭" @click="settingsOpen = false">
            <X :size="18" />
          </button>
        </div>

        <div class="form-grid">
          <label class="span-2">
            <span>API 地址</span>
            <input id="api-base" v-model="draft.apiBase" placeholder="http://127.0.0.1:8081" />
          </label>
          <label>
            <span>租户</span>
            <input v-model="draft.tenantId" required />
          </label>
          <label>
            <span>项目</span>
            <input v-model="draft.projectId" required />
          </label>
          <label>
            <span>主体</span>
            <input v-model="draft.principalId" required />
          </label>
          <label>
            <span>主体类型</span>
            <select v-model="draft.principalType">
              <option value="user">{{ labelPrincipalType("user") }}</option>
              <option value="service_account">{{ labelPrincipalType("service_account") }}</option>
            </select>
          </label>
          <label class="span-2">
            <span>访问令牌</span>
            <input v-model="draft.token" type="password" autocomplete="off" />
          </label>
          <label class="span-2">
            <span>权限范围</span>
            <textarea
              v-model="draft.scopes"
              rows="3"
              placeholder="data.dataset.read,data.dataset.create,..."
            />
          </label>
          <label class="span-2">
            <span>产品授权</span>
            <input v-model="draft.entitlements" placeholder="scenara.data" />
          </label>
        </div>

        <div class="modal-actions">
          <button type="button" class="button secondary" @click="testConnection">测试</button>
          <button class="button primary" type="submit">应用</button>
        </div>
      </form>
    </dialog>
  </div>
</template>
