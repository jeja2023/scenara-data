import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";
import { vCustomTooltip } from "./composables/useTooltip";

const app = createApp(App);
app.directive("tooltip", vCustomTooltip);
app.directive("custom-tooltip", vCustomTooltip);
app.use(router);
app.mount("#app");
