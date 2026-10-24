#!/usr/bin/env python3
"""Generate a random one-week menu.

Defaults to 7 days with three meals a day (breakfast / lunch / dinner), picked
from a built-in dish library. Within a single week the same meal slot will not
repeat a dish as long as its pool has at least ``days`` entries; when the pool is
smaller the generator degrades gracefully and allows repeats.

This module is pure Python 3 standard library. It does not call the Huawei Cloud
CLI, any Huawei Cloud SDK, or any REST API, and it touches no cloud resource.

Public API:
    load_dishes(path=None) -> dict[str, list[str]]
    pick_week(seed=None, days=7, meals=DEFAULT_MEALS, dedup=True, dishes=None) -> dict
    render_markdown(week) -> str
    render_text(week) -> str
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Dict, Iterable, List, Optional, Sequence

DEFAULT_MEALS: Sequence[str] = ("breakfast", "lunch", "dinner")
MEAL_LABELS: Dict[str, str] = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
}
MEAL_ORDER: Sequence[str] = ("breakfast", "lunch", "dinner")
WEEKDAYS: Sequence[str] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _default_dishes_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "dishes.json")


def load_dishes(path: Optional[str] = None) -> Dict[str, List[str]]:
    """Load the built-in dish library as ``{meal: [dish, ...]}``.

    Accepts either an explicit ``{"meals": {...}}`` wrapper or a flat mapping.
    Raises ``FileNotFoundError`` / ``ValueError`` on unusable input.
    """
    path = path or _default_dishes_path()
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    raw = data.get("meals", data) if isinstance(data, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ValueError("dish library must be a non-empty object keyed by meal")
    dishes: Dict[str, List[str]] = {}
    for meal, items in raw.items():
        if not isinstance(items, list):
            raise ValueError("dish list for %r must be an array" % meal)
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        if cleaned:
            dishes[str(meal)] = cleaned
    if not dishes:
        raise ValueError("dish library contains no usable dishes")
    return dishes


def _normalize_meals(meals: Iterable[str]) -> List[str]:
    if isinstance(meals, str):
        meals = [part.strip() for part in meals.split(",") if part.strip()]
    ordered: List[str] = []
    for meal in meals:
        meal = str(meal).strip()
        if meal and meal not in ordered:
            ordered.append(meal)
    return ordered or list(DEFAULT_MEALS)


def pick_week(
    seed: Optional[int] = None,
    days: int = 7,
    meals: Iterable[str] = DEFAULT_MEALS,
    dedup: bool = True,
    dishes: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, object]:
    """Pick a week of dishes.

    Returns a week object ``{"seed", "days", "meals", "dedup", "week"}`` where
    ``week`` is a list of ``{"day", "label", "meals": {meal: dish}}`` entries.
    ``seed`` is always concrete (a generated one is used when none is given) so
    the run can be reproduced with ``--seed``.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    meal_list = _normalize_meals(meals)
    dishes = dishes if dishes is not None else load_dishes()

    explicit_seed = seed is not None
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**31 - 1)
    rng = random.Random(seed)

    used: Dict[str, set] = {meal: set() for meal in meal_list}
    degraded: List[str] = []
    week: List[Dict[str, object]] = []

    for index in range(days):
        day_meals: Dict[str, str] = {}
        for meal in meal_list:
            pool = list(dishes.get(meal, []))
            if dedup:
                fresh = [dish for dish in pool if dish not in used[meal]]
                if fresh:
                    pool = fresh
                elif pool:
                    if meal not in degraded:
                        degraded.append(meal)
            if not pool:
                day_meals[meal] = "(no dish available)"
                continue
            choice = rng.choice(pool)
            used[meal].add(choice)
            day_meals[meal] = choice
        week.append(
            {
                "day": index + 1,
                "label": WEEKDAYS[index % len(WEEKDAYS)],
                "meals": day_meals,
            }
        )

    return {
        "seed": seed,
        "explicit_seed": explicit_seed,
        "days": days,
        "meals": meal_list,
        "dedup": bool(dedup),
        "degraded": sorted(degraded),
        "week": week,
    }


def _meal_label(meal: str) -> str:
    return MEAL_LABELS.get(meal, str(meal).capitalize())


def render_markdown(week: Dict[str, object]) -> str:
    """Render a week object as readable Markdown."""
    lines: List[str] = ["# Weekly Menu", ""]
    seed_note = "seed %s" % week["seed"]
    if not week.get("explicit_seed"):
        seed_note += " (auto-generated; rerun with --seed %s to reproduce)" % week["seed"]
    lines.append("- Days: %s" % week["days"])
    lines.append("- Meals: %s" % ", ".join(_meal_label(m) for m in week["meals"]))
    lines.append("- Same-meal de-dup within the week: %s" % ("on" if week["dedup"] else "off"))
    lines.append("- Random %s" % seed_note)
    if week.get("degraded"):
        lines.append(
            "- Note: dish pool too small for %s; repeats were allowed."
            % ", ".join(_meal_label(m) for m in week["degraded"])
        )
    lines.append("")
    for day in week["week"]:
        lines.append("## Day %s — %s" % (day["day"], day["label"]))
        for meal in week["meals"]:
            lines.append("- **%s**: %s" % (_meal_label(meal), day["meals"][meal]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_text(week: Dict[str, object]) -> str:
    """Render a week object as a plain-text menu."""
    lines: List[str] = ["Weekly Menu", "=" * 11]
    seed_note = "seed %s" % week["seed"]
    if not week.get("explicit_seed"):
        seed_note += " (auto-generated; rerun with --seed %s to reproduce)" % week["seed"]
    lines.append("Days: %s | Meals: %s" % (week["days"], ", ".join(week["meals"])))
    lines.append("Same-meal de-dup: %s | Random %s" % ("on" if week["dedup"] else "off", seed_note))
    if week.get("degraded"):
        lines.append("Note: repeats allowed for: %s" % ", ".join(week["degraded"]))
    lines.append("")
    for day in week["week"]:
        lines.append("Day %s (%s)" % (day["day"], day["label"]))
        for meal in week["meals"]:
            lines.append("  %-10s %s" % (_meal_label(meal) + ":", day["meals"][meal]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render(week: Dict[str, object], fmt: str = "markdown") -> str:
    if fmt == "text":
        return render_text(week)
    if fmt == "json":
        return json.dumps(week, ensure_ascii=False, indent=2)
    return render_markdown(week)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Randomly generate a one-week menu from a built-in dish library.",
    )
    parser.add_argument("--days", type=int, default=7, help="number of days (default: 7)")
    parser.add_argument(
        "--meals",
        default=",".join(DEFAULT_MEALS),
        help="comma-separated meal slots (default: breakfast,lunch,dinner)",
    )
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible output")
    parser.add_argument(
        "--format",
        choices=("markdown", "text", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="allow the same dish to repeat within the week",
    )
    parser.add_argument("--dishes", default=None, help="path to a custom dish library JSON")
    parser.add_argument("--output", default=None, help="write the menu to a file instead of stdout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        dishes = load_dishes(args.dishes)
    except (OSError, ValueError) as exc:
        print("error: cannot load dish library: %s" % exc, file=sys.stderr)
        return 2
    try:
        week = pick_week(
            seed=args.seed,
            days=args.days,
            meals=args.meals,
            dedup=not args.no_dedup,
            dishes=dishes,
        )
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    body = render(week, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(body)
        if args.format != "json":
            print("Seed: %s" % week["seed"])
            print("Wrote %s-day menu to %s" % (week["days"], args.output))
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())