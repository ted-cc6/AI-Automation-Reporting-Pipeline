"""Regression test for theme_tag_full_dataset's batch/merge wiring.

Real bug this caught: merge_batches was renamed from a private _merge_batches to a public
name (so it could also be called directly as a graph node), but the call inside
theme_tag_full_dataset was never updated -- it called the now-nonexistent _merge_batches and
would have raised NameError the moment anything actually reached that line with n > 0. Nothing
caught this because every existing test for this module only covers pure-logic helpers
(_pick_diverse_verbatims, _highest_severity), never theme_tag_full_dataset itself, since its
real path calls out to an LLM. Mocking out theme_tag_batch and merge_batches (both real,
already-tested-elsewhere functions) verifies the wiring between them without any network call.
"""

from unittest.mock import patch

from qualitative_agent.agent import theme_tag_full_dataset
from qualitative_agent.data_prep import FreeTextResponse
from schemas.common import QualitativeSynthesis


def _response(i: int) -> FreeTextResponse:
    return FreeTextResponse(
        client_id=str(i),
        text=f"response {i}",
        source_field="test_field",
        gender=None,
        age=None,
        branch=None,
        country=None,
        loan_cycle=None,
    )


def test_theme_tag_full_dataset_calls_the_real_merge_batches_function():
    responses = [_response(i) for i in range(5)]
    fake_batch_result = QualitativeSynthesis(source_field="batch", base_n=5, themes=[])
    fake_merged = QualitativeSynthesis(source_field="merged", base_n=5, themes=[])

    with patch("qualitative_agent.agent.theme_tag_batch", return_value=fake_batch_result) as mock_batch, \
         patch("qualitative_agent.agent.merge_batches", return_value=fake_merged) as mock_merge:
        result = theme_tag_full_dataset("test_section", responses, "task instructions", batch_size=200)

    assert result is fake_merged
    mock_batch.assert_called_once()
    mock_merge.assert_called_once_with("test_section", [fake_batch_result], 5, "high")


def test_theme_tag_full_dataset_splits_into_multiple_batches():
    responses = [_response(i) for i in range(10)]
    fake_batch_result = QualitativeSynthesis(source_field="batch", base_n=1, themes=[])

    with patch("qualitative_agent.agent.theme_tag_batch", return_value=fake_batch_result) as mock_batch, \
         patch("qualitative_agent.agent.merge_batches", return_value=fake_batch_result) as mock_merge:
        theme_tag_full_dataset("test_section", responses, "task instructions", batch_size=3)

    assert mock_batch.call_count == 4  # 3+3+3+1
    mock_merge.assert_called_once()
    assert len(mock_merge.call_args[0][1]) == 4  # 4 batch results passed through


def test_theme_tag_full_dataset_empty_input_short_circuits_without_calling_merge():
    with patch("qualitative_agent.agent.merge_batches") as mock_merge:
        result = theme_tag_full_dataset("test_section", [], "task instructions")

    assert result.base_n == 0
    assert result.themes == []
    mock_merge.assert_not_called()
