"""提供方中立指标注册表（指南 11.3 `GET /metrics`）。

业务代码只依赖 `MetricsRegistry`，不绑定具体导出实现。第一阶段以 Prometheus 文本格式
暴露；OpenTelemetry 导出接入见 `docs/adr/0005-observability-baseline.md`。
"""

from __future__ import annotations

from threading import RLock

#: 直方图默认分桶（毫秒），覆盖 API 与发布路径的常见延迟区间。
DEFAULT_BUCKETS_MS = (5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0)

Labels = tuple[tuple[str, str], ...]


def _normalize(labels: dict[str, str] | None) -> Labels:
    if not labels:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _render_labels(labels: Labels) -> str:
    if not labels:
        return ""
    body = ",".join(f'{key}="{_escape(value)}"' for key, value in labels)
    return "{" + body + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    """线程安全的计数器 / 量表 / 直方图集合。"""

    def __init__(self, *, buckets_ms: tuple[float, ...] = DEFAULT_BUCKETS_MS) -> None:
        self._lock = RLock()
        self._buckets = tuple(sorted(buckets_ms))
        self._help: dict[str, str] = {}
        self._counters: dict[tuple[str, Labels], float] = {}
        self._gauges: dict[tuple[str, Labels], float] = {}
        self._histograms: dict[tuple[str, Labels], list[float]] = {}
        self._histogram_sums: dict[tuple[str, Labels], float] = {}
        self._histogram_counts: dict[tuple[str, Labels], int] = {}

    def describe(self, name: str, help_text: str) -> None:
        with self._lock:
            self._help[name] = help_text

    def increment(self, name: str, *, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        if value < 0:
            raise ValueError("计数器不能递减")
        identity = (name, _normalize(labels))
        with self._lock:
            self._counters[identity] = self._counters.get(identity, 0.0) + value

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        identity = (name, _normalize(labels))
        with self._lock:
            self._gauges[identity] = float(value)

    def observe(self, name: str, value_ms: float, *, labels: dict[str, str] | None = None) -> None:
        identity = (name, _normalize(labels))
        with self._lock:
            counts = self._histograms.setdefault(identity, [0.0] * len(self._buckets))
            for index, bound in enumerate(self._buckets):
                if value_ms <= bound:
                    counts[index] += 1
            self._histogram_sums[identity] = self._histogram_sums.get(identity, 0.0) + value_ms
            self._histogram_counts[identity] = self._histogram_counts.get(identity, 0) + 1

    def counter_value(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        return self._counters.get((name, _normalize(labels)), 0.0)

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {
                "counters": {f"{name}{_render_labels(labels)}": value for (name, labels), value in self._counters.items()},
                "gauges": {f"{name}{_render_labels(labels)}": value for (name, labels), value in self._gauges.items()},
                "histogram_counts": {
                    f"{name}{_render_labels(labels)}": float(value)
                    for (name, labels), value in self._histogram_counts.items()
                },
            }

    def render(self) -> str:
        return render_prometheus(self)

    # 渲染需要访问内部结构，仅供同模块 render_prometheus 使用。
    def _export(
        self,
    ) -> tuple[
        tuple[float, ...],
        dict[str, str],
        dict[tuple[str, Labels], float],
        dict[tuple[str, Labels], float],
        dict[tuple[str, Labels], list[float]],
        dict[tuple[str, Labels], float],
        dict[tuple[str, Labels], int],
    ]:
        with self._lock:
            return (
                self._buckets,
                dict(self._help),
                dict(self._counters),
                dict(self._gauges),
                {key: list(value) for key, value in self._histograms.items()},
                dict(self._histogram_sums),
                dict(self._histogram_counts),
            )


def render_prometheus(registry: MetricsRegistry) -> str:
    buckets, help_texts, counters, gauges, histograms, sums, counts = registry._export()
    lines: list[str] = []

    for kind, series in (("counter", counters), ("gauge", gauges)):
        for name in sorted({item[0] for item in series}):
            if name in help_texts:
                lines.append(f"# HELP {name} {help_texts[name]}")
            lines.append(f"# TYPE {name} {kind}")
            for (metric, labels), value in sorted(series.items()):
                if metric != name:
                    continue
                lines.append(f"{name}{_render_labels(labels)} {_format_number(value)}")

    for name in sorted({item[0] for item in histograms}):
        if name in help_texts:
            lines.append(f"# HELP {name} {help_texts[name]}")
        lines.append(f"# TYPE {name} histogram")
        for (metric, labels), bucket_counts in sorted(histograms.items()):
            if metric != name:
                continue
            for bound, count in zip(buckets, bucket_counts, strict=True):
                bucket_labels = labels + (("le", _format_number(bound)),)
                lines.append(f"{name}_bucket{_render_labels(bucket_labels)} {_format_number(count)}")
            total = counts.get((metric, labels), 0)
            lines.append(f"{name}_bucket{_render_labels(labels + (('le', '+Inf'),))} {_format_number(float(total))}")
            lines.append(f"{name}_sum{_render_labels(labels)} {_format_number(sums.get((metric, labels), 0.0))}")
            lines.append(f"{name}_count{_render_labels(labels)} {_format_number(float(total))}")

    return "\n".join(lines) + "\n" if lines else "# 尚未记录指标\n"


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(round(value, 6))
