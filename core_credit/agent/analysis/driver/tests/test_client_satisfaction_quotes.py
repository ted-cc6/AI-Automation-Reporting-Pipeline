"""CC-091: 8.2's quote block, chosen in code."""

from driver.build_client_satisfaction import _pick_driver_verbatims, _without_quotes
from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim


def _v(q):
    return Verbatim(quote=q, country="KEN", source_field="f")


def _q(*themes):
    return QualitativeSynthesis(
        source_field="f", base_n=10,
        themes=[ThemeFinding(theme=f"t{i}", frequency=5 - i, representative_verbatims=vs) for i, vs in enumerate(themes)],
    )


def test_top_theme_quote_from_each_side_in_order():
    promoters = _q([_v("good service always")], [_v("fast loans")])
    detractors = _q([], [_v("interest is too high")])  # top theme has no quote: take the next
    assert [v.quote for v in _pick_driver_verbatims(promoters, detractors)] == ["good service always", "interest is too high"]


def test_missing_side_is_skipped():
    assert [v.quote for v in _pick_driver_verbatims(_q([_v("good service always")]), _q())] == ["good service always"]


def test_insight_pool_drops_quotes_shown_in_8_2():
    pool = _q([_v("good service always"), _v("very kind staff here")])
    kept = _without_quotes(pool, [_v("good service always")])
    assert [v.quote for v in kept.themes[0].representative_verbatims] == ["very kind staff here"]
    assert len(pool.themes[0].representative_verbatims) == 2  # original untouched
