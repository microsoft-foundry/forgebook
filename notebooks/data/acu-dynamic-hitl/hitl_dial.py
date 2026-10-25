"""Notebook display helpers: the coverage dial and accessible charts, with no JavaScript.

Every dial position is precomputed from the same calibration code the notebook
runs. Radio buttons and CSS sibling selectors switch between positions, so the
dial stays interactive in Jupyter, VS Code, and sanitized static renderers that
strip scripts. Without CSS, every position renders as a plain stacked list.
"""

from __future__ import annotations

import base64
import io
from html import escape
from typing import Iterable, Mapping

import matplotlib.pyplot as plt
import pandas as pd

import calibration as calib

FIELD_LABELS = {
    "menu.name": "Item name",
    "menu.price": "Item price",
    "menu.quantity": "Item quantity",
    "subtotal_price": "Subtotal",
    "tax_price": "Tax",
    "service_price": "Service charge",
    "other_adjustment": "Discount",
    "total_price": "Total",
}

BLANK = "#0078d4"
FILLED = "#107c10"
REVIEWED = "#c7cdd4"
MISTAKE = "#d13438"

DEFAULT_TARGETS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99)


def dial_positions(
    base_policies: Mapping[str, Mapping],
    data: pd.DataFrame,
    targets: Iterable[float] = DEFAULT_TARGETS,
) -> list[dict]:
    """Expected savings on the training split and measured results on the held-out split, per target."""
    train = calib.calibration_input(data, split="train")
    positions = []
    for target in targets:
        policies = calib.select_policies(base_policies, target)
        per_field, portfolio = calib.savings_attribution(policies, train)
        _, held_out = calib.held_out_metrics(calib.route_frame(data, policies, split="test"))
        table = calib.calibration_table(policies).set_index("field_name")
        fields = []
        for row in per_field.itertuples():
            n_total = max(int(row.n_total), 1)
            cutoff = table.loc[row.field, "cutoff"] if row.field in table.index else None
            fields.append(
                {
                    "label": FIELD_LABELS.get(row.field, row.field),
                    "blank": row.null_savings / n_total,
                    "filled": row.lr_savings / n_total,
                    "cutoff": None if cutoff is None or pd.isna(cutoff) else float(cutoff),
                }
            )
        positions.append(
            {
                "target": target,
                "avoided": portfolio["hitl_savings_pct"],
                "blank": portfolio["null_savings_pct"],
                "filled": portfolio["lr_savings_pct"],
                "values_avoided": int(round(portfolio["hitl_savings_pct"] * len(train))),
                "caught": held_out["catch_rate"],
                "slipped": held_out["stp_error_rate"],
                "fields_with_cutoff": int((table["filled_decision"] == "calibrate").sum()),
                "n_fields": len(table),
                "fields": fields,
            }
        )
    return positions


def _bar(blank: float, filled: float, height: int, label: str) -> str:
    blank_w = max(blank, 0.0) * 100
    filled_w = max(filled, 0.0) * 100
    return (
        f'<svg class="hd-bar" viewBox="0 0 100 {height}" preserveAspectRatio="none" '
        f'width="100%" height="{height}" role="img" aria-label="{escape(label)}">'
        f'<rect x="0" y="0" width="100" height="{height}" fill="{REVIEWED}"></rect>'
        f'<rect x="0" y="0" width="{blank_w:.2f}" height="{height}" fill="{BLANK}"></rect>'
        f'<rect x="{blank_w:.2f}" y="0" width="{filled_w:.2f}" height="{height}" fill="{FILLED}"></rect>'
        "</svg>"
    )


def _panel(position: dict, key: str) -> str:
    p = position
    portfolio_label = (
        f"{p['blank']:.0%} blank values auto-approved, {p['filled']:.0%} filled-in values "
        f"auto-approved, {1 - p['avoided']:.0%} still reviewed"
    )
    rows = []
    for field in p["fields"]:
        decision = f"cutoff {field['cutoff']:.3f}" if field["cutoff"] is not None else "no cutoff"
        share = field["blank"] + field["filled"]
        bar = _bar(field["blank"], field["filled"], 10, "%s: %.0f%% auto-approved" % (field["label"], share * 100))
        rows.append(
            '<div class="hd-field">'
            f'<span class="hd-fname">{escape(field["label"])}</span>'
            f'<span class="hd-fbar">{bar}</span>'
            f'<span class="hd-fval">{share:.0%} · {escape(decision)}</span>'
            "</div>"
        )
    return (
        f'<div class="hd-panel hd-p{key}">'
        f'<p class="hd-heading">At a <strong>{p["target"]:.0%}</strong> catch target</p>'
        '<div class="hd-metrics">'
        f'<div><span class="hd-k">Review avoided</span><span class="hd-v">{p["avoided"]:.1%}</span>'
        f'<span class="hd-s">{p["values_avoided"]:,} training values never reach a person</span></div>'
        f'<div><span class="hd-k">From blank values</span><span class="hd-v" style="color:{BLANK}">{p["blank"]:.1%}</span></div>'
        f'<div><span class="hd-k">From filled-in values</span><span class="hd-v" style="color:{FILLED}">{p["filled"]:.1%}</span>'
        f'<span class="hd-s">{p["fields_with_cutoff"]} of {p["n_fields"]} fields earned a cutoff</span></div>'
        "</div>"
        f"{_bar(p['blank'], p['filled'], 18, portfolio_label)}"
        '<div class="hd-legend">'
        f'<span><i style="background:{BLANK}"></i>Blank (auto-approved)</span>'
        f'<span><i style="background:{FILLED}"></i>Filled-in (auto-approved)</span>'
        f'<span><i style="background:{REVIEWED}"></i>Still reviewed by a person</span>'
        "</div>"
        '<div class="hd-metrics hd-heldout">'
        f'<div><span class="hd-k">Caught on unseen documents</span><span class="hd-v" style="color:{FILLED}">{p["caught"]:.1%}</span></div>'
        f'<div><span class="hd-k">Slipped through</span><span class="hd-v" style="color:{MISTAKE}">{p["slipped"]:.1%}</span>'
        '<span class="hd-s">of auto-approved values were wrong</span></div>'
        "</div>"
        f'<div class="hd-fields">{"".join(rows)}</div>'
        "</div>"
    )


def render_dial(positions: list[dict], *, default: float = 0.80, dial_id: str = "hd") -> str:
    """Return the dial as one HTML fragment: radio buttons, CSS, and one panel per position."""
    keys = [f"{round(p['target'] * 100):d}" for p in positions]
    default_key = f"{round(default * 100):d}"
    inputs = "".join(
        f'<input class="hd-radio" type="radio" name="{dial_id}-target" id="{dial_id}-t{k}"'
        f'{" checked" if k == default_key else ""}>'
        for k in keys
    )
    labels = "".join(f'<label for="{dial_id}-t{k}">{k}%</label>' for k in keys)
    show = ",".join(f"#{dial_id}-t{k}:checked ~ .hd-panels .hd-p{k}" for k in keys)
    active = ",".join(f'#{dial_id}-t{k}:checked ~ .hd-stops label[for="{dial_id}-t{k}"]' for k in keys)
    focus = ",".join(f'#{dial_id}-t{k}:focus-visible ~ .hd-stops label[for="{dial_id}-t{k}"]' for k in keys)
    css = f"""
.hitl-dial{{position:relative;border:1px solid rgba(127,127,127,.35);border-radius:12px;padding:16px 18px;margin:8px 0;font-size:14px;line-height:1.4}}
.hitl-dial .hd-radio{{position:absolute;opacity:0;width:1px;height:1px;margin:0;pointer-events:none}}
.hitl-dial .hd-set{{border:0;margin:0;padding:0;min-width:0}}
.hitl-dial .hd-title{{margin:0 0 8px;padding:0;font-weight:600}}
.hitl-dial .hd-stops{{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}}
.hitl-dial .hd-stops label{{cursor:pointer;padding:4px 10px;border:1px solid rgba(127,127,127,.45);border-radius:999px;font-variant-numeric:tabular-nums;margin:0}}
.hitl-dial .hd-ends{{display:flex;justify-content:space-between;font-size:12px;opacity:.75;margin:0 0 12px}}
{active}{{background:{BLANK};border-color:{BLANK};color:#fff;font-weight:600}}
{focus}{{outline:2px solid {BLANK};outline-offset:2px}}
.hitl-dial .hd-panel{{display:none}}
{show}{{display:block}}
.hitl-dial .hd-heading{{margin:0 0 10px}}
.hitl-dial .hd-metrics{{display:flex;flex-wrap:wrap;gap:12px 28px;margin:0 0 12px}}
.hitl-dial .hd-metrics>div{{display:flex;flex-direction:column;min-width:150px}}
.hitl-dial .hd-k{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;opacity:.75}}
.hitl-dial .hd-v{{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}}
.hitl-dial .hd-s{{font-size:12px;opacity:.75}}
.hitl-dial .hd-bar{{display:block;border-radius:4px}}
.hitl-dial .hd-legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;margin:8px 0 14px}}
.hitl-dial .hd-legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}}
.hitl-dial .hd-heldout{{border-top:1px solid rgba(127,127,127,.3);padding-top:10px}}
.hitl-dial .hd-fields{{display:grid;gap:6px}}
.hitl-dial .hd-field{{display:grid;grid-template-columns:120px 1fr 170px;gap:10px;align-items:center;font-size:13px}}
.hitl-dial .hd-fval{{font-variant-numeric:tabular-nums;opacity:.85}}
@media (max-width:560px){{.hitl-dial .hd-field{{grid-template-columns:96px 1fr}}.hitl-dial .hd-fval{{grid-column:2}}}}
"""
    panels = "".join(_panel(p, k) for p, k in zip(positions, keys))
    return (
        f'<div class="hitl-dial" id="{dial_id}">'
        f"<style>{css}</style>"
        '<fieldset class="hd-set">'
        '<legend class="hd-title">Share of known mistakes human review must catch</legend>'
        f"{inputs}"
        f'<div class="hd-stops">{labels}</div>'
        '<div class="hd-ends"><span>automate more</span><span>catch more</span></div>'
        f'<div class="hd-panels">{panels}</div>'
        "</fieldset>"
        "</div>"
    )


def figure_html(fig, alt: str, *, dpi: int = 110) -> str:
    """Return a Matplotlib figure as an <img> with alt text, and close the figure.

    Static notebook renderers often drop alt text from image outputs, so the
    chart is inlined as a data URI inside HTML that carries its description.
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="{escape(alt)}" style="max-width:100%;height:auto">'
