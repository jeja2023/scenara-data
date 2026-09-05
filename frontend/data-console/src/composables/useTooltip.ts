import { ref, type Directive } from "vue";

export interface TooltipState {
  visible: boolean;
  text: string;
  x: number;
  y: number;
  placement: "top" | "bottom";
}

const tooltipState = ref<TooltipState>({
  visible: false,
  text: "",
  x: 0,
  y: 0,
  placement: "top",
});

let hideTimer: number | null = null;

export function showTooltip(target: HTMLElement, text: string): void {
  if (!text || !text.trim()) return;
  if (hideTimer) {
    window.clearTimeout(hideTimer);
    hideTimer = null;
  }
  const rect = target.getBoundingClientRect();
  const screenWidth = window.innerWidth;
  
  // Calculate center X coordinate with screen bounds protection
  let centerX = rect.left + rect.width / 2;
  if (centerX < 60) centerX = 60;
  if (centerX > screenWidth - 60) centerX = screenWidth - 60;

  // Decide whether to show on top or bottom
  let placement: "top" | "bottom" = "top";
  let targetY = rect.top - 8;
  if (rect.top < 40) {
    placement = "bottom";
    targetY = rect.bottom + 8;
  }

  tooltipState.value = {
    visible: true,
    text,
    x: Math.round(centerX),
    y: Math.round(targetY),
    placement,
  };
}

export function hideTooltip(): void {
  hideTimer = window.setTimeout(() => {
    tooltipState.value.visible = false;
  }, 60);
}

export function useTooltip() {
  return {
    tooltipState,
    showTooltip,
    hideTooltip,
  };
}

/**
 * Vue 3 Directive: v-custom-tooltip="text"
 */
export const vCustomTooltip: Directive<HTMLElement, string | undefined | null> = {
  mounted(el, binding) {
    el.addEventListener("mouseenter", () => {
      const text = binding.value || el.getAttribute("data-tooltip") || el.innerText;
      if (text) {
        showTooltip(el, text);
      }
    });
    el.addEventListener("mouseleave", () => {
      hideTooltip();
    });
  },
  updated(el, binding) {
    if (binding.value !== binding.oldValue && tooltipState.value.visible) {
      const text = binding.value || el.getAttribute("data-tooltip") || el.innerText;
      if (text) {
        tooltipState.value.text = text;
      }
    }
  },
  beforeUnmount(el) {
    el.removeEventListener("mouseenter", () => {});
    el.removeEventListener("mouseleave", () => {});
  },
};
