import { onBeforeUnmount, onMounted } from "vue";

export const REFRESH_EVENT = "scenara:data-refresh";

export function useRefresh(handler: () => void | Promise<void>): void {
  const listener = () => {
    void handler();
  };
  onMounted(() => window.addEventListener(REFRESH_EVENT, listener));
  onBeforeUnmount(() => window.removeEventListener(REFRESH_EVENT, listener));
}

