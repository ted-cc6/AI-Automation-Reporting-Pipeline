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


def _base_analysis(report_scope=None, **overrides) -> dict:
    analysis = {
        "meta": {"report_scope": report_scope},
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
                    # Deliberately not 0.5 like the metric above -- a tie here
                    # would trip _disambiguate_tied_percentages() and this
                    # fixture is meant for plain 1-decimal formatting tests.
                    # See TestDisambiguateTiedPercentages below for the tie case.
                    "worth_premium": {"headline": _metric(0.62, 500)},
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
            "First-Time Access to Insurance",
            "Worth the Premium",
            "Claim Process Understanding",
            "Children's Wellbeing Improved",
        ]

    def test_values_formatted_correctly(self):
        rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert rows["First-Time Access to Insurance"]["value"] == "80.0%"
        assert rows["Worth the Premium"]["value"] == "62.0%"
        assert rows["Claim Process Understanding"]["value"] == "50.0%"
        assert rows["Children's Wellbeing Improved"]["value"] == "35.0%"
        # "n" is each row's own stated base (n_valid), already the correct
        # denominator of its own percentage in every case -- R-002's session-2
        # correction found this was already true; the real gap was that a
        # restricted-base row (Children's Wellbeing, on child_wellbeing_base)
        # was rendered identically to a full-sample row, with no way for a
        # reader to tell them apart. See base_label below and R-002 in
        # docs/report_spec.md.
        assert rows["First-Time Access to Insurance"]["n"] == 500
        assert rows["Children's Wellbeing Improved"]["n"] == 400

    def test_base_label_null_for_full_sample_metric(self):
        rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert rows["First-Time Access to Insurance"]["base_label"] == ""
        assert rows["Claim Process Understanding"]["base_label"] == ""

    def test_base_label_static_phrase_for_restricted_metric(self):
        rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert rows["Children's Wellbeing Improved"]["base_label"] == "clients with children in household"

    def test_base_label_worth_premium_resolves_by_report_scope(self):
        # worth_premium's base_label is a {default, lacro} dict in
        # report_spec.yaml, resolved the same way every population: note
        # already is (generation/orchestrator.py's _resolve_population()) --
        # a LACRO-scoped report is 100% Health, so no restriction applies.
        lacro_rows = {r["label"]: r for r in headline_numbers(_base_analysis(report_scope="lacro"))}
        assert lacro_rows["Worth the Premium"]["base_label"] == ""

        default_rows = {r["label"]: r for r in headline_numbers(_base_analysis(report_scope="africa"))}
        assert default_rows["Worth the Premium"]["base_label"] == "Health & credit-life clients only"

        unset_rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert unset_rows["Worth the Premium"]["base_label"] == "Health & credit-life clients only"

    def test_not_applicable_metric_omitted_not_shown_as_na(self):
        analysis = _base_analysis()
        analysis["parts"]["part_1"]["metrics"]["claim_process_understanding"] = {"headline": _metric(
            None, 0, suppressed=True, not_applicable=True
        )}
        rows = headline_numbers(analysis)
        labels = [r["label"] for r in rows]
        assert "Claim Process Understanding" not in labels
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


class TestDisambiguateTiedPercentages:
    def test_rows_tied_at_one_decimal_get_a_second_decimal(self):
        # Real production values from runs/lacro_final_check/: worth_premium
        # =0.8006972690296339 and claim_process_understanding=
        # 0.8012783265543288 both round to "80.1%" at 1 decimal, reading like
        # a copy-paste error in a 4-row table. Only these two rows should
        # gain a second decimal; the other two, untied, stay at 1 decimal.
        analysis = _base_analysis()
        analysis["parts"]["part_1"]["metrics"]["worth_premium"] = {
            "headline": _metric(0.8006972690296339, 1721)
        }
        analysis["parts"]["part_1"]["metrics"]["claim_process_understanding"] = {
            "headline": _metric(0.8012783265543288, 1721)
        }
        rows = {r["label"]: r for r in headline_numbers(analysis)}
        assert rows["Worth the Premium"]["value"] == "80.07%"
        assert rows["Claim Process Understanding"]["value"] == "80.13%"
        assert rows["First-Time Access to Insurance"]["value"] == "80.0%"
        assert rows["Children's Wellbeing Improved"]["value"] == "35.0%"

    def test_untied_rows_stay_at_one_decimal(self):
        # Default fixture: no two rows tie at 1 decimal (worth_premium=62.0%
        # is distinct from claim_process_understanding=50.0%) -- nothing
        # should be bumped to 2 decimals.
        rows = {r["label"]: r for r in headline_numbers(_base_analysis())}
        assert rows["Worth the Premium"]["value"] == "62.0%"
        assert rows["Claim Process Understanding"]["value"] == "50.0%"
        assert rows["First-Time Access to Insurance"]["value"] == "80.0%"
        assert rows["Children's Wellbeing Improved"]["value"] == "35.0%"

    def test_suppressed_rows_do_not_trigger_disambiguation(self):
        # Two rows both rendering "SUPPRESSED" is not a rounding collision --
        # bumping decimal places on a non-numeric string would be meaningless.
        analysis = _base_analysis()
        analysis["parts"]["part_1"]["metrics"]["worth_premium"] = {
            "headline": _metric(None, 0, suppressed=True)
        }
        analysis["parts"]["part_3"]["metrics"]["no_prior_access"] = {
            "headline": _metric(None, 0, suppressed=True)
        }
        rows = {r["label"]: r for r in headline_numbers(analysis)}
        assert rows["Worth the Premium"]["value"] == "SUPPRESSED"
        assert rows["First-Time Access to Insurance"]["value"] == "SUPPRESSED"

    def test_three_way_tie_bumps_all_three(self):
        # All three round to "50.0%" at 1 decimal (second decimal digit < 5
        # in each), but differ from the third decimal onward.
        analysis = _base_analysis()
        analysis["parts"]["part_1"]["metrics"]["worth_premium"] = {"headline": _metric(0.50001, 500)}
        analysis["parts"]["part_1"]["metrics"]["claim_process_understanding"] = {"headline": _metric(0.50023, 500)}
        analysis["parts"]["part_3"]["metrics"]["no_prior_access"] = {"headline": _metric(0.50044, 500)}
        rows = {r["label"]: r for r in headline_numbers(analysis)}
        assert rows["Worth the Premium"]["value"] == "50.00%"
        assert rows["Claim Process Understanding"]["value"] == "50.02%"
        assert rows["First-Time Access to Insurance"]["value"] == "50.04%"


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
