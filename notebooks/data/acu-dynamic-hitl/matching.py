"""Decide whether an extracted value matches ground truth.

The calibration never compares extractions to ground truth itself -- it consumes
the ``is_correct`` column and calibrates against it. This module produces that
column: **exact match after normalization**, so that cosmetic differences
(currency symbols, casing, stray whitespace, thousands separators) are not
counted as extraction mistakes.

These are the rules that produced ``is_correct`` for the bundled receipts, and
running :func:`add_is_correct` over that dataset reproduces every one of its
13,853 labels. Normalization is not cosmetic there: it decides 2.4% of the
verdicts, mostly quantities where ground truth reads ``1 x`` and the extraction
reads ``1 X`` or ``1 ×``. For strict string equality instead, pass a normalizer
that only handles blanks::

    matching.add_is_correct(
        data, normalizer=lambda v, field: None if matching.is_null(v) else str(v)
    )

Typical use, once you have a frame of extractions paired with ground truth::

    import matching

    data = matching.add_is_correct(data)

List fields, such as receipt line items, need pairing first. Extractions add,
drop, and reorder lines, so pair extracted items with ground-truth items by
content with :func:`pair_with_ground_truth`, not by position, and then call
:func:`add_is_correct`.

Which normalizer runs is chosen per field, by looking for tokens in the field
name (see :data:`FIELD_RULES`). Adapt those rules -- or pass your own
``normalizer`` -- so the definition of "correct" here is the same one your
business already uses. Everything downstream inherits it: too strict and the
calibration chases mistakes that were never mistakes, too loose and it certifies
real ones as correct.
"""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


Normalizer = Callable[[Any], str | None]


def is_null(value: Any) -> bool:
    """True when a value counts as "nothing was extracted"."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, str):
        return not value.strip()
    return False


def normalize_text(value: Any) -> str | None:
    """Case-fold, collapse whitespace, and apply Unicode NFKC."""
    if is_null(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_quantity(value: Any) -> str | None:
    """Pull the leading number out of values like ``"1 x"`` or ``"x2"``."""
    text = normalize_text(value)
    if text is None:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
    if not match:
        return text
    number = match.group(0).replace(",", ".")
    try:
        quantity = Decimal(number)
    except InvalidOperation:
        return text
    return format(quantity.normalize(), "f")


def normalize_money(value: Any) -> str | None:
    """Strip currency symbols and separators down to a comparable number.

    Handles both decimal conventions (``1.234,56`` and ``1,234.56``) and treats
    a leading ``-`` or surrounding parentheses as negative.
    """
    text = normalize_text(value)
    if text is None:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned:
        return text
    cleaned = cleaned.replace("-", "")
    if "," in cleaned and "." in cleaned:
        # Whichever separator comes last is the decimal point.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") > 1:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[1]
        cleaned = (
            cleaned.replace(",", ".")
            if len(tail) in (1, 2)
            else cleaned.replace(",", "")
        )
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return text
    if negative:
        amount = -amount
    return format(amount.normalize(), "f")


# Tokens searched for in the field name, in order, to pick a normalizer.
# Extend this for your own schema -- dates, account numbers, postcodes, and
# similar domain formats belong here rather than in the calibration.
FIELD_RULES: tuple[tuple[tuple[str, ...], Normalizer], ...] = (
    (("price", "total", "tax", "service", "amount"), normalize_money),
    (("quantity", ".cnt", "_count"), normalize_quantity),
)

DEFAULT_NORMALIZER: Normalizer = normalize_text


def normalizer_for(field_name: str) -> Normalizer:
    """The normalizer that :func:`normalize_value` would use for a field."""
    lower = str(field_name).casefold()
    for tokens, normalizer in FIELD_RULES:
        if any(token in lower for token in tokens):
            return normalizer
    return DEFAULT_NORMALIZER


def normalize_value(value: Any, field_name: str) -> str | None:
    """Normalize one value the way its field expects."""
    return normalizer_for(field_name)(value)


def values_match(ground_truth: Any, extracted: Any, field_name: str) -> bool:
    """Whether an extraction should count as correct for this field.

    Two blanks match: when the extraction is empty and ground truth is empty
    too, the model was right to return nothing. That is the quantity the blank
    routing track is calibrated on.
    """
    return normalize_value(ground_truth, field_name) == normalize_value(
        extracted, field_name
    )


def add_is_correct(
    frame: pd.DataFrame,
    *,
    ground_truth_column: str = "ground_truth_value",
    extracted_column: str = "extracted_value",
    field_column: str = "field_name",
    normalizer: Callable[[Any, str], str | None] | None = None,
) -> pd.DataFrame:
    """Return a copy of ``frame`` with an ``is_correct`` column filled in.

    Pass ``normalizer`` -- any ``(value, field_name) -> comparable`` callable --
    to swap in your own matching rules wholesale.
    """
    missing = [
        column
        for column in (ground_truth_column, extracted_column, field_column)
        if column not in frame.columns
    ]
    if missing:
        raise KeyError(f"frame is missing required columns: {missing}")

    normalize = normalizer or normalize_value
    result = frame.copy()
    result["is_correct"] = [
        normalize(ground_truth, field) == normalize(extracted, field)
        for ground_truth, extracted, field in zip(
            result[ground_truth_column],
            result[extracted_column],
            result[field_column],
        )
    ]
    return result


# ---------------------------------------------------------------------------
# Line items (list fields)
# ---------------------------------------------------------------------------

#: Default cost above which a ground-truth item and an extracted item are not
#: paired. Unpaired items are kept: a ground-truth item becomes ``missed`` and
#: an extracted item becomes ``extra``.
DEFAULT_MAX_PAIR_COST = 0.65


def _item_property_score(
    prop: str, ground_truth: Any, extracted: Any, *, fuzzy: bool
) -> float:
    """Agreement between two values of one item property, from 0 to 1."""
    if fuzzy:
        left = normalize_value(ground_truth, prop) or ""
        right = normalize_value(extracted, prop) or ""
        return SequenceMatcher(None, left, right).ratio()
    return 1.0 if normalize_value(ground_truth, prop) == normalize_value(extracted, prop) else 0.0


def align_line_items(
    ground_truth_items: Sequence[Mapping[str, Any]],
    extracted_items: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, float] | None = None,
    fuzzy: Sequence[str] | None = None,
    max_cost: float = DEFAULT_MAX_PAIR_COST,
) -> list[tuple[int | None, int | None]]:
    """Pair ground-truth line items with extracted line items by content.

    Each item is a mapping of property name to value, for example
    ``{"name": "Coffee", "quantity": "1", "price": "5.00"}``. Position in the
    list is ignored: extractions add, drop, and reorder lines, so pairing by
    index would shift every later item and mislabel correct values.

    The cost of pairing two items is the weighted share of properties that
    disagree. Properties in ``fuzzy`` score by text similarity (0 to 1) after
    normalization; the rest score 1 on an exact match after normalization and 0
    otherwise. By default every property gets weight 1, and properties whose
    normalizer is plain text are fuzzy.

    The pairing is one-to-one and minimizes total cost (the Hungarian
    algorithm), so no ground-truth item is credited twice. Pairs that cost more
    than ``max_cost`` are split. No item is ever dropped: the result lists every
    ground-truth index and every extracted index exactly once, as
    ``(gt_index, extracted_index)``, with ``None`` on the side that has no
    partner. Matched pairs come first in ground-truth order, then missed
    ground-truth items, then extra extracted items.
    """
    ground_truth_items = [dict(item) for item in ground_truth_items]
    extracted_items = [dict(item) for item in extracted_items]
    if not ground_truth_items:
        return [(None, index) for index in range(len(extracted_items))]
    if not extracted_items:
        return [(index, None) for index in range(len(ground_truth_items))]

    if weights is None:
        properties = sorted(set().union(*ground_truth_items, *extracted_items))
        weights = {prop: 1.0 for prop in properties}
    weights = {prop: float(weight) for prop, weight in weights.items()}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive number")
    if fuzzy is None:
        fuzzy_properties = {
            prop for prop in weights if normalizer_for(prop) is DEFAULT_NORMALIZER
        }
    else:
        fuzzy_properties = set(fuzzy)

    costs = np.zeros((len(ground_truth_items), len(extracted_items)))
    for gt_index, gt_item in enumerate(ground_truth_items):
        for extracted_index, extracted_item in enumerate(extracted_items):
            disagreement = sum(
                weight
                * (
                    1.0
                    - _item_property_score(
                        prop,
                        gt_item.get(prop),
                        extracted_item.get(prop),
                        fuzzy=prop in fuzzy_properties,
                    )
                )
                for prop, weight in weights.items()
            )
            costs[gt_index, extracted_index] = disagreement / total_weight

    matched_gt: set[int] = set()
    matched_extracted: set[int] = set()
    pairs: list[tuple[int | None, int | None]] = []
    row_indices, column_indices = linear_sum_assignment(costs)
    for gt_index, extracted_index in sorted(zip(row_indices, column_indices)):
        # The tolerance keeps a pair that sits exactly on the threshold from
        # flipping on floating-point rounding.
        if costs[gt_index, extracted_index] <= max_cost + 1e-9:
            matched_gt.add(int(gt_index))
            matched_extracted.add(int(extracted_index))
            pairs.append((int(gt_index), int(extracted_index)))
    pairs.extend(
        (index, None) for index in range(len(ground_truth_items)) if index not in matched_gt
    )
    pairs.extend(
        (None, index)
        for index in range(len(extracted_items))
        if index not in matched_extracted
    )
    return pairs


def pair_with_ground_truth(
    extracted: pd.DataFrame,
    ground_truth: pd.DataFrame,
    *,
    weights: Mapping[str, float] | None = None,
    fuzzy: Sequence[str] | None = None,
    max_cost: float = DEFAULT_MAX_PAIR_COST,
) -> pd.DataFrame:
    """Attach ground truth to extracted rows, pairing list fields by content.

    ``extracted`` has one row per extracted value, with ``document_id``,
    ``field_name``, ``item_index``, ``extracted_value``, and ``confidence``
    (the shape step 7's ``to_canonical_rows`` produces). ``ground_truth`` has
    ``document_id``, ``field_name``, ``item_index``, and
    ``ground_truth_value``. ``item_index`` is empty for single-value fields.

    Single-value fields are joined on ``document_id`` and ``field_name``. List
    fields are named ``<list>.<property>`` (for example ``menu.price``); within
    each document and list, items are paired with :func:`align_line_items`, and
    ``weights`` and ``fuzzy`` are keyed by property name.

    The result has one row per value with a ``line_item_status`` column:
    ``matched``, ``missed`` (in ground truth, never extracted), or ``extra``
    (extracted, not in ground truth), and empty for single-value fields.
    ``item_index`` is renumbered in pairing order. Add ``split`` and call
    :func:`add_is_correct` next.
    """
    extracted = extracted.copy()
    ground_truth = ground_truth.copy()
    for frame, name in ((extracted, "extracted"), (ground_truth, "ground_truth")):
        if "item_index" not in frame.columns:
            frame["item_index"] = np.nan
        required = ["document_id", "field_name", "item_index"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise KeyError(f"{name} is missing required columns: {missing}")
    if "confidence" not in extracted.columns:
        extracted["confidence"] = np.nan

    def is_list(frame: pd.DataFrame) -> pd.Series:
        return frame["item_index"].notna()

    scalars = pd.merge(
        extracted.loc[~is_list(extracted), ["document_id", "field_name", "extracted_value", "confidence"]],
        ground_truth.loc[~is_list(ground_truth), ["document_id", "field_name", "ground_truth_value"]],
        on=["document_id", "field_name"],
        how="outer",
    )
    scalars["item_index"] = np.nan
    scalars["line_item_status"] = None

    def items_by_group(frame: pd.DataFrame, value_column: str) -> dict:
        grouped: dict[tuple[str, str], dict[Any, dict[str, Any]]] = {}
        listed = frame.loc[is_list(frame)]
        for row in listed.itertuples(index=False):
            group, _, prop = str(row.field_name).partition(".")
            if not prop:
                raise ValueError(
                    f"list field {row.field_name!r} must be named <list>.<property>"
                )
            entry = grouped.setdefault((row.document_id, group), {}).setdefault(
                row.item_index, {}
            )
            entry[prop] = getattr(row, value_column)
            if value_column == "extracted_value":
                entry.setdefault("__confidence__", {})[prop] = row.confidence
        return {
            key: [items[index] for index in sorted(items)] for key, items in grouped.items()
        }

    extracted_groups = items_by_group(extracted, "extracted_value")
    truth_groups = items_by_group(ground_truth, "ground_truth_value")
    list_rows: list[dict[str, Any]] = []
    for key in sorted(set(extracted_groups) | set(truth_groups), key=str):
        document_id, group = key
        truth_items = truth_groups.get(key, [])
        extracted_items = extracted_groups.get(key, [])
        plain_extracted = [
            {prop: value for prop, value in item.items() if prop != "__confidence__"}
            for item in extracted_items
        ]
        properties = sorted(
            set().union(*truth_items, *plain_extracted) if (truth_items or plain_extracted) else set()
        )
        pairs = align_line_items(
            truth_items, plain_extracted, weights=weights, fuzzy=fuzzy, max_cost=max_cost
        )
        for item_index, (gt_index, extracted_index) in enumerate(pairs):
            truth_item = truth_items[gt_index] if gt_index is not None else {}
            extracted_item = extracted_items[extracted_index] if extracted_index is not None else {}
            status = (
                "matched"
                if gt_index is not None and extracted_index is not None
                else ("missed" if extracted_index is None else "extra")
            )
            for prop in properties:
                list_rows.append(
                    {
                        "document_id": document_id,
                        "field_name": f"{group}.{prop}",
                        "item_index": item_index,
                        "ground_truth_value": truth_item.get(prop),
                        "extracted_value": extracted_item.get(prop),
                        "confidence": extracted_item.get("__confidence__", {}).get(prop, np.nan),
                        "line_item_status": status,
                    }
                )
    columns = [
        "document_id",
        "field_name",
        "item_index",
        "ground_truth_value",
        "extracted_value",
        "confidence",
        "line_item_status",
    ]
    return pd.concat(
        [scalars[columns], pd.DataFrame(list_rows, columns=columns)], ignore_index=True
    )
