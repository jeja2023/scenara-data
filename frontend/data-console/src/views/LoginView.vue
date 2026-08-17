<script setup lang="ts">
import { Eye, EyeOff, LogIn, ShieldCheck } from "@lucide/vue";
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { completeSignIn } from "../auth";
import { ApiError, loadConnection, login, userFacingError } from "../api";
import brandMark from "../assets/scenara-mark.svg";

const route = useRoute();
const router = useRouter();
const savedConnection = loadConnection();
const form = reactive({
  username: savedConnection.principalId === "data-console" ? "admin" : savedConnection.principalId || "admin",
  password: "",
  apiBase: savedConnection.apiBase,
});
const remember = ref(false);
const revealPassword = ref(false);
const submitting = ref(false);
const errorMessage = ref("");
const passwordInput = ref<HTMLInputElement | null>(null);
const destination = computed(() => {
  const requested = typeof route.query.redirect === "string" ? route.query.redirect : "/";
  return requested.startsWith("/") && !requested.startsWith("//") && requested !== "/login"
    ? requested
    : "/";
});

function togglePasswordVisibility(): void {
  revealPassword.value = !revealPassword.value;
  void nextTick(() => passwordInput.value?.focus());
}

async function submit(): Promise<void> {
  if (submitting.value) return;
  submitting.value = true;
  errorMessage.value = "";
  try {
    const apiBase = form.apiBase.replace(/\/$/, "");
    const session = await login(form.username.trim(), form.password, { apiBase });
    completeSignIn(
      {
        ...loadConnection(),
        apiBase,
        token: session.token,
        tenantId: session.session.tenant_id,
        projectId: session.session.project_id,
        principalId: session.session.user_id,
        principalType: session.session.principal_type,
        scopes: session.session.permission_scopes.join(","),
        entitlements: session.session.product_entitlements.join(","),
      },
      remember.value,
      session.expires_at,
    );
    form.password = "";
    await router.replace(destination.value);
  } catch (caught) {
    errorMessage.value =
      caught instanceof ApiError && caught.status === 401
        ? "用户名或密码错误"
        : userFacingError(caught, "登录失败，请稍后重试");
  } finally {
    submitting.value = false;
  }
}

onMounted(() => passwordInput.value?.focus());
</script>

<template>
  <main class="login-page">
    <section class="login-brand-pane" aria-label="Scenara 景枢">
      <div class="login-brand-lockup">
        <img :src="brandMark" alt="" />
        <div><strong>Scenara</strong><span>景枢数据</span></div>
      </div>
      <div class="login-brand-message">
        <p>数据管理工作台</p>
        <h1>连接视觉<br />理解世界</h1>
      </div>
      <div class="login-brand-footer">
        <ShieldCheck :size="17" />
        <span>本地工作台会话</span>
      </div>
    </section>

    <section class="login-form-pane">
      <div class="login-mobile-brand">
        <img :src="brandMark" alt="" />
        <div><strong>Scenara</strong><span>景枢数据</span></div>
      </div>

      <form class="login-form" aria-label="登录" @submit.prevent="submit">
        <header>
          <p>Scenara Data Console</p>
          <h2>登录数据工作台</h2>
          <span>使用用户名和密码进入当前数据平台。</span>
        </header>

        <div class="login-field">
          <label for="username">用户名</label>
          <input id="username" v-model="form.username" autocomplete="username" required />
        </div>

        <div class="login-field">
          <label for="password">密码</label>
          <span class="login-password-field">
            <input
              id="password"
              ref="passwordInput"
              v-model="form.password"
              :type="revealPassword ? 'text' : 'password'"
              autocomplete="current-password"
              required
            />
            <button
              type="button"
              :title="revealPassword ? '隐藏密码' : '显示密码'"
              :aria-label="revealPassword ? '隐藏密码' : '显示密码'"
              @click="togglePasswordVisibility"
            >
              <EyeOff v-if="revealPassword" :size="18" />
              <Eye v-else :size="18" />
            </button>
          </span>
        </div>

        <details class="login-advanced">
          <summary>连接设置</summary>
          <div class="login-field">
            <label for="login-api-base">API 地址</label>
            <input id="login-api-base" v-model="form.apiBase" placeholder="http://127.0.0.1:8081" />
          </div>
        </details>

        <label class="login-remember">
          <input v-model="remember" type="checkbox" />
          <span>保持登录</span>
        </label>

        <p v-if="errorMessage" class="login-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="login-submit" type="submit" :disabled="submitting">
          <LogIn :size="18" />
          {{ submitting ? "正在登录" : "登录" }}
        </button>
      </form>

      <footer class="login-form-footer">景枢数据 · v0.1.4</footer>
    </section>
  </main>
</template>
