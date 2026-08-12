from schemas.common import MetricResult, SegmentAxis, SegmentedValue

from graph.checkpointing import sqlite_checkpointer


class _NotRegisteredAnywhere:
    """Deliberately NOT in ALLOWED_CHECKPOINT_TYPES -- module-level (not defined inside a
    test function) because pickle can't serialize a class local to a function at all,
    independent of anything this module is actually testing.
    """

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, _NotRegisteredAnywhere) and self.value == other.value


def test_sqlite_checkpointer_round_trips_a_registered_custom_type(tmp_path):
    db_path = str(tmp_path / "test_checkpoints.db")
    mr = MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.9, n=100),
    )
    with sqlite_checkpointer(db_path) as checkpointer:
        dumped_type, dumped = checkpointer.serde.dumps_typed(mr)
        loaded = checkpointer.serde.loads_typed((dumped_type, dumped))
        assert loaded == mr


def test_sqlite_checkpointer_falls_back_to_pickle_for_unregistered_types(tmp_path):
    # Regression test: SectionConfig carries a raw `type` object (schema_class) and
    # MetricConfig carries `frozenset` fields -- neither is msgpack-native and neither is
    # practical to enumerate in ALLOWED_CHECKPOINT_TYPES. Without pickle_fallback=True this
    # raised MsgpackEncodeError and crashed a real run; this locks in the fix.
    db_path = str(tmp_path / "test_checkpoints_fallback.db")

    with sqlite_checkpointer(db_path) as checkpointer:
        obj = _NotRegisteredAnywhere(frozenset({"a", "b"}))
        dumped_type, dumped = checkpointer.serde.dumps_typed(obj)
        loaded = checkpointer.serde.loads_typed((dumped_type, dumped))
        assert loaded == obj


def test_sqlite_checkpointer_is_usable_by_a_compiled_graph(tmp_path):
    from graph.graph import compile_graph

    db_path = str(tmp_path / "test_checkpoints2.db")
    with sqlite_checkpointer(db_path) as checkpointer:
        graph = compile_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "test-thread"}}
        snapshot = graph.get_state(config)
        assert snapshot.values == {}  # nothing checkpointed yet for a fresh thread_id
