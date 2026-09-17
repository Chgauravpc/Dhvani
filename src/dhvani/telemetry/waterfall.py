"""ASCII Gantt rendering of a single turn's spans and marks."""

from __future__ import annotations

from dhvani.telemetry.span import TurnTrace

_LABEL = "  {stage:<8} {name:<9}"
_LABEL_WIDTH = len(_LABEL.format(stage="", name=""))
_N_TICKS = 3


def render(trace: TurnTrace, width: int = 72) -> str:
    """Render a pure-ASCII Gantt chart of one turn, positioned by absolute time.

    Spans are drawn in the order they were recorded, each on its own row, so
    concurrent spans visibly occupy overlapping columns. The critical path
    (see `TurnTrace.critical_path`) is annotated. Output is deterministic for
    a fixed trace, so it renders identically in a Windows terminal, a GitHub
    README code block, and a snapshot test.
    """
    bar_chars = max(width - _LABEL_WIDTH - 10, 10)

    timestamps = [trace.t0_ns]
    for s in trace.spans:
        timestamps.append(s.start_ns)
        if s.end_ns is not None:
            timestamps.append(s.end_ns)
    for m in trace.marks:
        timestamps.append(m.at_ns)
    span_ns = max(max(timestamps) - trace.t0_ns, 1)

    def col(at_ns: int) -> int:
        rel_ns = min(max(at_ns - trace.t0_ns, 0), span_ns)
        return round(rel_ns / span_ns * bar_chars)

    critical_ids = {id(s) for s in trace.critical_path()}

    ttfa = trace.ttfa_ms
    ttfa_str = f"{ttfa:.1f}ms" if ttfa is not None else "n/a"
    lines = [f"turn {trace.turn_id}  t0=0.0ms  TTFA={ttfa_str}"]

    ruler = [" "] * bar_chars
    for i in range(_N_TICKS + 1):
        tick_ms = span_ns / 1_000_000 * i / _N_TICKS
        label = f"{tick_ms:.0f}ms"
        tick_col = min(round(i / _N_TICKS * bar_chars), max(bar_chars - len(label), 0))
        for j, ch in enumerate(label):
            if tick_col + j < bar_chars:
                ruler[tick_col + j] = ch
    lines.append(" " * _LABEL_WIDTH + "".join(ruler))

    for s in trace.spans:
        bar = ["."] * bar_chars
        start_col = col(s.start_ns)
        end_col = col(s.end_ns) if s.end_ns is not None else bar_chars
        for c in range(start_col, max(end_col, start_col + 1)):
            if c < bar_chars:
                bar[c] = "#"
        label = _LABEL.format(stage=s.stage.value, name=s.name)
        dur_str = f"{s.duration_ms:.1f}ms" if s.duration_ms is not None else "open"
        suffix = "  <- critical" if id(s) in critical_ids else ""
        lines.append(f"{label}|{''.join(bar)}|  {dur_str}{suffix}")

    for m in trace.marks:
        rel_ms = (m.at_ns - trace.t0_ns) / 1_000_000
        lines.append(f"  ^ {m.name} at {rel_ms:.1f}ms")

    return "\n".join(lines)
