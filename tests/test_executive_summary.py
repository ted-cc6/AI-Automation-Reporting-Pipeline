"""
Unit tests for generation/executive_summary.py -- deterministic headline
numbers + data-availability caveat box (Phase D). Core guarantee: a metric
that is not_applicable to this run's dataset schema must be omitted from
headline_numbers (not shown as N/A), and must show up by its precise human
label in data_availability_caveats instead.
Run: pytest tests/test_executive_summary.py -v
"""
from __future__ import annotations

from generation.executive_summary import data_availability_caveats, headline_numbers


def _metric(value, n_valid, suppressed=False, not_applicable=False):
    return {"value": value, "n_valid": n_valid, "suppressed": suppressed, "not_applicable": not_applicable}


def _base_analysis(**overrides) -> dict:
    analysis = {
        "parts": {
            "part_4": {
                "nps": {"result": _metric(20.0, 500)},
                "child_wellbeing": {"headline": _metric(0.35, 400)},
            },
            "part_3": {
                "metrics": {
                    "no_prior_access": {"headline": _metric(0.8, 500)},
                    "confidence_pay": {"headline": _metric(0.6, 500)},
                    "negative_coping": {"headline": _metric(0.1, 200)},
                }
            },
            "part_2": {
                "claims_funnel": {
                    "filed_claim": {
                        "n": 100, "n_total": 500, "pct_of_event_base": 0.2,
                        "suppressed": False, "not_applicable": False,
                    },
                    "experienced_event": _metric(400, 500),
                    "claim_paid": _metric(0.7, 100),
                    "payout_adequacy": {"n_valid": 80, "suppressed": False, "not_applicable": False},
                }
            },
            "part_1": {
                "metrics": {
                    "coverage_understanding": {"headline": _metric(0.5, 500)},
                    "claim_process_understanding": {"headline": _metric(0.5, 500)},
                    "worth_premium": {"headline": _metric(0.5, 500)},
                    "renewal_intent": {"headline": _metric(0.5, 500)},
                    "product_understanding": {"headline": _metric(None, 0, suppressed=True, not_applicable=True)},
                }
            },
        }
    }
    analysis.update(overrides)
    return analysis


class TestHeadlineNumbers:
    def test_all_applicable_metrics_included(self):
        rows = headline_numbers(_base_analysis())
        labels = [r["label"] for r in rows]
        assert labels == [
            "Net Promoter Score",
            "Children's Wellbeing Improved",
            "First-Time Access to Insurance",
            "Filed a Claim",
        ]

    def test_values_formatted_correctly(self):
        rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert rows["Net Promoter Score"]["value"] == "20.0"
        assert rows["Children's Wellbeing Improved"]["value"] == "35.0%"
        assert rows["Filed a Claim"]["value"] == "20.0%"
        # "n" is the row's stated BASE (n_total = 500, the insured-event
        # population this 20% is computed against), not the numerator (100
        # clients who filed) -- a real generated report once showed "Filed a
        # Claim | 44.4% | 55" where 55 was the numerator and the true base
        # was 124, misleading a reader into thinking N=55 respondents were
        # asked this question.
        assert rows["Filed a Claim"]["n"] == 500

    def test_not_applicable_metric_omitted_not_shown_as_na(self):
        analysis = _base_analysis()
        analysis["parts"]["part_4"]["nps"]["result"] = _metric(
            None, 0, suppressed=True, not_applicable=True
        )
        rows = headline_numbers(analysis)
        labels = [r["label"] for r in rows]
        assert "Net Promoter Score" not in labels
        assert len(rows) == 3

    def test_missing_data_entirely_shows_suppressed_not_silently_empty(self):
        # A totally empty parts dict is not the same as an explicit
        # not_applicable flag -- format_value()'s own v-is-None fallback
        # marks each row SUPPRESSED, so a malformed/incomplete
        # analysis_results.json is loudly visible rather than silently
        # rendering an empty headline-numbers box.
        rows = headline_numbers({"parts": {}})
        assert len(rows) == 4
        assert all(r["value"] == "SUPPRESSED" for r in rows)


class TestDataAvailabilityCaveats:
    def test_larco_like_schema_lists_all_africa_only_metrics(self):
        analysis = _base_analysis()
        # A real LARCO run has product_understanding (it's LARCO-only) --
        # flip it back to applicable so this fixture mirrors the real
        # exclusive-or relationship between the two schemas' field sets.
        analysis["parts"]["part_1"]["metrics"]["product_understanding"] = {"headline": _metric(0.14, 1355)}
        for path_parts in [
            ("part_1", "metrics", "coverage_understanding", "headline"),
            ("part_1", "metrics", "claim_process_understanding", "headline"),
            ("part_1", "metrics", "worth_premium", "headline"),
            ("part_1", "metrics", "renewal_intent", "headline"),
            ("part_3", "metrics", "confidence_pay", "headline"),
            ("part_3", "metrics", "negative_coping", "headline"),
        ]:
            node = analysis["parts"]
            for key in path_parts[:-1]:
                node = node[key]
            node[path_parts[-1]] = _metric(None, 0, suppressed=True, not_applicable=True)
        analysis["parts"]["part_2"]["claims_funnel"]["experienced_event"] = _metric(
            None, 0, suppressed=True, not_applicable=True
        )
        analysis["parts"]["part_2"]["claims_funnel"]["claim_paid"] = _metric(
            None, 0, suppressed=True, not_applicable=True
        )
        analysis["parts"]["part_2"]["claims_funnel"]["payout_adequacy"] = {
            "n_valid": 0, "suppressed": True, "not_applicable": True,
        }
        caveats = data_availability_caveats(analysis)
        assert set(caveats) == {
            "Coverage Understanding", "Claim Process Understanding", "Worth Premium",
            "Renewal Intent (not collected by the LACRO survey instrument)",
            "Confidence in Payout", "Negative Coping",
            "Experienced Insured Event (claims funnel step)", "Claim Paid Outcome",
            "Payout Adequacy",
        }

    def test_africa_like_schema_lists_only_product_understanding(self):
        caveats = data_availability_caveats(_base_analysis())
        # Carries a cross-reference note pointing at Part 1's two split
        # metrics -- without it, the caveat box's "does not collect ... so
        # they do not appear elsewhere in this report" sentence reads as
        # contradicting Part 1's own product-understanding reporting a few
        # pages away (see generation/executive_summary.py's
        # _NOT_APPLICABLE_CANDIDATES comment).
        assert caveats == [
            "Combined Product Understanding (reported instead in Part 1 as two split "
            "metrics, Coverage Understanding and Claim Process Understanding)"
        ]

    def test_no_data_returns_empty_list(self):
        assert data_availability_caveats({"parts": {}}) == []
