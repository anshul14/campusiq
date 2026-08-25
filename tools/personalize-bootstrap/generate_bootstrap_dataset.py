#!/usr/bin/env python3
"""
generate_bootstrap_dataset.py

Generates SYNTHETIC ENGAGEMENT HISTORY for real bootstrap student accounts,
sized to clear Personalize's published training minimum (1000 interactions,
25 distinct users with 2+ interactions each). Run
provision_bootstrap_students.py FIRST -- this script reads the real Cognito
subs it creates from bootstrap_students.json rather than inventing string
IDs, so Personalize trains against actual platform identities, not
fabricated ones. Only the ENGAGEMENT is synthetic (no one has genuinely
used the platform yet); the STUDENT IDENTITIES are real accounts this
tooling owns and later tears down. See README.md for the full disclosure.

Design: 3 behavioral cohorts, so the trained model has genuine signal to
learn from rather than one flat pattern that "proves" nothing:
  - friction : heavy repeat engagement with week3-friction-remediation
  - inertia  : heavy repeat engagement with week3-inertia-remediation
  - balanced : even light engagement across all items, no concentration

Validation later checks that get_recommendations (or batch inference) for a
friction-cohort user ranks week3-friction-remediation visibly higher than it
does for an inertia-cohort user -- that's the actual proof point, not just
"training succeeded."

Outputs (Personalize bulk-import CSV format):
    interactions.csv  -- USER_ID, ITEM_ID, TIMESTAMP, EVENT_TYPE, EVENT_VALUE
    items.csv         -- ITEM_ID, concept, difficulty
"""

import csv
import json
import random
from datetime import datetime, timedelta, timezone

random.seed(42)  # reproducible — same dataset every run, easier to reason about

OUTPUT_DIR = "."
ROSTER_FILE = "bootstrap_students.json"

# Reuses the exact module IDs already committed to in ARCHITECTURE.md section
# 3.3's example, plus a mirrored inertia-remediation item since our real
# validated test data (Gap Detection, test-student-3) centers on friction/
# inertia specifically.
ITEMS = [
    {"item_id": "week3-friction-remediation", "concept": "friction", "difficulty": "easy"},
    {"item_id": "week3-inertia-remediation", "concept": "inertia", "difficulty": "easy"},
    {"item_id": "week3-newtons-laws", "concept": "general", "difficulty": "medium"},
    {"item_id": "week4-forces", "concept": "forces", "difficulty": "medium"},
    {"item_id": "week2-dynamics-review", "concept": "general", "difficulty": "easy"},
]

BASE_DATE = datetime(2026, 5, 1, tzinfo=timezone.utc)
SPREAD_DAYS = 45  # interactions spread across ~6 weeks, like real usage would be


def make_interactions_for_student(user_id: str, cohort: str) -> list[dict]:
    """
    Returns a list of interaction rows for one simulated student.
    Heavy-engagement item gets 8-12 repeat interactions (representing
    repeated study sessions on a weak concept); every other item gets
    2-3 light interactions. Balanced-cohort students get 3-5 on every
    item, no concentration.
    """
    rows = []

    if cohort == "friction":
        heavy_item, light_items = "week3-friction-remediation", [i["item_id"] for i in ITEMS if i["item_id"] != "week3-friction-remediation"]
    elif cohort == "inertia":
        heavy_item, light_items = "week3-inertia-remediation", [i["item_id"] for i in ITEMS if i["item_id"] != "week3-inertia-remediation"]
    else:  # balanced
        heavy_item, light_items = None, [i["item_id"] for i in ITEMS]

    def add_events(item_id: str, count: int):
        for _ in range(count):
            offset_days = random.uniform(0, SPREAD_DAYS)
            ts = BASE_DATE + timedelta(days=offset_days)
            rows.append({
                "USER_ID": user_id,
                "ITEM_ID": item_id,
                "TIMESTAMP": int(ts.timestamp()),
                "EVENT_TYPE": "MODULE_ENGAGEMENT",
                "EVENT_VALUE": round(random.uniform(0.4, 1.0), 2),  # engagement strength
            })

    if heavy_item:
        add_events(heavy_item, random.randint(16, 20))
        for item_id in light_items:
            add_events(item_id, random.randint(4, 6))
    else:
        for item_id in light_items:
            add_events(item_id, random.randint(6, 8))

    return rows


def load_roster() -> dict:
    try:
        with open(ROSTER_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(
            f"\n{ROSTER_FILE} not found. Run provision_bootstrap_students.py first -- "
            "this script needs real Cognito subs to generate engagement history for, "
            "not fabricated string IDs."
        )


def main():
    roster = load_roster()  # {"friction": [{"username":..., "sub":...}, ...], "inertia": [...], "balanced": [...]}
    interactions = []

    for cohort, students in roster.items():
        for entry in students:
            interactions.extend(make_interactions_for_student(entry["sub"], cohort))

    with open(f"{OUTPUT_DIR}/interactions.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["USER_ID", "ITEM_ID", "TIMESTAMP", "EVENT_TYPE", "EVENT_VALUE"])
        writer.writeheader()
        writer.writerows(interactions)

    with open(f"{OUTPUT_DIR}/items.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ITEM_ID", "concept", "difficulty"])
        writer.writeheader()
        for item in ITEMS:
            writer.writerow({"ITEM_ID": item["item_id"], "concept": item["concept"], "difficulty": item["difficulty"]})

    total_users = sum(len(v) for v in roster.values())
    print(f"Generated {len(interactions)} interactions across {total_users} real bootstrap student accounts.")
    print(f"Minimum required: 1000 interactions, 25 users -- "
          f"{'PASS' if len(interactions) >= 1000 and total_users >= 25 else 'FAIL, adjust repeat counts in make_interactions_for_student'}")

    # Print a couple of example rows per cohort so it's easy to sanity-check
    # by eye that the heavy-engagement pattern actually landed correctly.
    from collections import Counter
    for cohort, students in roster.items():
        sample_sub = students[0]["sub"]
        sample_username = students[0]["username"]
        sample_rows = [r for r in interactions if r["USER_ID"] == sample_sub]
        print(f"\n{cohort} sample ({sample_username}, {len(sample_rows)} interactions):")
        counts = Counter(r["ITEM_ID"] for r in sample_rows)
        for item_id, count in counts.most_common():
            print(f"  {item_id}: {count}")


if __name__ == "__main__":
    main()