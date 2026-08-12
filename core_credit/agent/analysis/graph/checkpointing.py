"""SQLite checkpointer factory with the custom types this graph's state actually holds
registered explicitly.

Without this, langgraph-checkpoint's default serializer falls back to pickling any type it
doesn't recognize (our Pydantic schema classes, the FreeTextResponse dataclass) and prints
"this will be blocked in a future version" on every single deserialization -- confirmed on a
real run. Registering the common ones via `allowed_msgpack_modules` silences that warning for
them specifically.

`pickle_fallback=True` is deliberately also set: the generalized, config-driven state is
richer than the original Part-3-only version -- SectionConfig carries a raw `type` object
(the schema class itself) and MetricConfig carries `frozenset` fields, neither of which are
msgpack-native and neither of which is practical to enumerate in the allowlist below (unlike
named Pydantic/dataclass instances, "every frozenset anywhere in state" isn't a fixed, listable
set of types). Without pickle_fallback, encoding one of those raises MsgpackEncodeError and
the whole run crashes -- confirmed by hitting exactly that on a real run before adding this.
The allowlist below still does real work: it silences the warning for the types we can name;
pickle_fallback is the safety net for everything else, at the cost of a warning instead of
silence for those long-tail cases.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

# Every custom type that can end up in GraphState (see state.py) and therefore needs to
# survive a checkpoint round-trip. Extend this list if a future section's state introduces
# a new schema type -- an unregistered type still works (via pickle fallback), it just prints
# the deprecation warning again until added here.
ALLOWED_CHECKPOINT_TYPES = [
    ("schemas.common", "SegmentAxis"),
    ("schemas.common", "SegmentedValue"),
    ("schemas.common", "MetricResult"),
    ("schemas.common", "BenchmarkComparison"),
    ("schemas.common", "SignificanceResult"),
    ("schemas.common", "GapComparison"),
    ("schemas.common", "RankedOption"),
    ("schemas.common", "RankedOptions"),
    ("schemas.common", "QualitativeSynthesis"),
    ("schemas.common", "ThemeFinding"),
    ("schemas.common", "Verbatim"),
    ("schemas.common", "WrittenText"),
    ("schemas.common", "SectionStatus"),
    ("schemas.business_household_impact", "BusinessHouseholdImpactSection"),
    ("schemas.financial_access", "FinancialAccessSection"),
    ("schemas.child_wellbeing", "ChildWellbeingSection"),
    ("schemas.client_protection", "ClientProtectionSection"),
    ("schemas.agency", "AgencySection"),
    ("schemas.resilience", "ResilienceSection"),
    ("qualitative_agent.data_prep", "FreeTextResponse"),
    ("section_configs.config", "MetricConfig"),
    ("section_configs.config", "QualitativeConfig"),
    ("section_configs.config", "SectionConfig"),
    ("writer.section_prompts", "SubsectionPrompt"),
]


@contextmanager
def sqlite_checkpointer(db_path: str) -> Iterator[SqliteSaver]:
    """Same usage as SqliteSaver.from_conn_string(db_path), but with our types registered
    against the deprecation-warning fallback path.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        serde = JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES, pickle_fallback=True)
        yield SqliteSaver(conn, serde=serde)
    finally:
        conn.close()
