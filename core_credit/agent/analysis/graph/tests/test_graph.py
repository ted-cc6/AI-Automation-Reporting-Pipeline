from graph.graph import build_graph, compile_graph


def test_build_graph_has_every_expected_node():
    g = build_graph()
    assert set(g.nodes.keys()) == {
        "load_data_node",
        "compute_metric_node",
        "metrics_ready_node",
        "theme_tag_batch_node",
        "merge_qualitative_node",
        "skip_qualitative_node",
        "write_subsection_node",
        "write_insight_node",
        "assemble_section_node",
    }


def test_compile_graph_succeeds_without_a_checkpointer():
    compiled = compile_graph()
    assert compiled is not None


def test_compile_graph_accepts_a_checkpointer():
    from langgraph.checkpoint.memory import InMemorySaver

    compiled = compile_graph(checkpointer=InMemorySaver())
    assert compiled is not None
