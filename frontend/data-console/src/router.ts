import { createRouter, createWebHistory } from "vue-router";
import {
  Activity,
  Database,
  FileClock,
  FlaskConical,
  LayoutDashboard,
  Layers3,
  Settings2,
} from "@lucide/vue";

import { isSignedIn } from "./auth";

const APP_TITLE = "景枢数据";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("./views/LoginView.vue"),
    meta: {
      title: "登录",
      hideFromNavigation: true,
      public: true,
      layout: "auth",
      platform: "data",
    },
  },
  {
    path: "/",
    name: "overview",
    component: () => import("./views/OverviewView.vue"),
    meta: {
      title: "总览",
      description: "查看数据平台运行状态、最新数据集和最近处理概览。",
      icon: LayoutDashboard,
      section: "工作台",
      platform: "data",
    },
  },
  {
    path: "/datasets",
    name: "datasets",
    component: () => import("./views/DatasetsView.vue"),
    meta: {
      title: "数据集",
      description: "创建、查看并推进数据集生命周期。",
      icon: Database,
      section: "数据管理",
      platform: "data",
    },
  },
  {
    path: "/versions",
    name: "versions",
    component: () => import("./views/VersionsView.vue"),
    meta: {
      title: "版本治理",
      description: "管理构建、校验、发布和版本引用。",
      icon: Layers3,
      section: "数据管理",
      platform: "data",
    },
  },
  {
    path: "/hard-samples",
    name: "hard-samples",
    component: () => import("./views/HardSamplesView.vue"),
    meta: {
      title: "难例导入",
      description: "接收已批准的难例清单并检查导入结果。",
      icon: FlaskConical,
      section: "迁移与导入",
      platform: "data",
    },
  },
  {
    path: "/operations",
    name: "operations",
    component: () => import("./views/OperationsView.vue"),
    meta: {
      title: "运维探针",
      description: "查看依赖就绪检查与服务状态。",
      icon: Activity,
      section: "运维与健康",
      platform: "data",
    },
  },
  {
    path: "/settings",
    redirect: "/operations",
    meta: {
      title: "设置",
      description: "连接参数和访问凭据。",
      icon: Settings2,
      section: "运维与健康",
      platform: "data",
      hideFromNavigation: true,
    },
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
] as const;

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

router.beforeEach((to) => {
  if (!to.meta.public && !isSignedIn()) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && isSignedIn()) return { name: "overview" };
  return true;
});

router.afterEach((to) => {
  const title = String(to.meta.title ?? APP_TITLE);
  document.title = `${title} · ${APP_TITLE}`;
});

export { routes };
export default router;
