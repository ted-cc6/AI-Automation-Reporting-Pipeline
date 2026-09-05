"""CC-035: the SubsectionPrompt banned-term guard. chain.py already runs validate_subsection_prompts()
against the real section_prompts module at import time -- these tests exercise the checker function
itself against synthetic modules, so a real violation is provable independent of the current (clean)
state of section_prompts.py.
"""
import types

import pytest

from writer.chain import CC001_BANNED_TERMS, CC003_BANNED_TERMS, validate_subsection_prompts
from writer.section_prompts import SubsectionPrompt


def _module_with(**prompts):
    module = types.SimpleNamespace()
    for name, prompt in prompts.items():
        setattr(module, name, prompt)
    return module


def test_passes_on_a_clean_module():
    module = _module_with(
        OK=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="Report the figure and note any pattern by gender."),
    )
    validate_subsection_prompts(module)  # must not raise


def test_catches_a_banned_term_in_instructions():
    module = _module_with(
        BAD=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="This causes the outcome to improve."),
    )
    with pytest.raises(ValueError, match="causes"):
        validate_subsection_prompts(module)


def test_catches_a_banned_term_in_the_title():
    module = _module_with(
        BAD=SubsectionPrompt(subsection_id="x.1", title="What drives the outcome", word_cap=80, instructions="Report the figure."),
    )
    with pytest.raises(ValueError, match="drives"):
        validate_subsection_prompts(module)


def test_catches_a_cc003_competitive_verb():
    module = _module_with(
        BAD=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="Our figure outpaces the benchmark."),
    )
    with pytest.raises(ValueError, match="outpaces"):
        validate_subsection_prompts(module)


def test_catches_leverage_standalone_not_only_the_exact_carries_the_most_leverage_phrase():
    # CC-030's real 8.2/8-insight defect: "the fix with the most leverage" contains the banned
    # word but not SYSTEM_PROMPT's literal 4-word phrase "carries the most leverage".
    module = _module_with(
        BAD=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="Name the fix with the most leverage."),
    )
    with pytest.raises(ValueError, match="leverage"):
        validate_subsection_prompts(module)


def test_catches_leading_to_not_only_the_literal_leads_to():
    # CC-030's real 4.1 defect: the prompt used "leading to", not the literal "leads to".
    module = _module_with(
        BAD=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="For example higher income leading to better outcomes."),
    )
    with pytest.raises(ValueError, match="leading to"):
        validate_subsection_prompts(module)


def test_does_not_flag_a_noun_lead_followed_by_to_as_a_different_object():
    # A genuine false-positive risk for a naive "lead to" match: "flip from a non-caregiver
    # lead to caregivers ahead" uses "lead" as a noun (an advantage), not the causal verb
    # construction -- confirmed as a real false positive hit during CC-035's own rollout, fixed
    # by rewording the prompt rather than the checker, since the checker being wrong here would
    # have meant either missing "leading to" above or firing on this legitimate sentence too. A
    # `\blead to\b` phrase match can't tell the two apart, so this test locks the checker's
    # actual literal-match behavior in, and the corresponding prompt was reworded (see 4.2 in
    # section_prompts.py) to route around it rather than the checker being taught grammar.
    module = _module_with(
        OK=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions="The rate flips from favoring non-caregivers to caregivers ahead."),
    )
    validate_subsection_prompts(module)  # must not raise


def test_ignores_non_subsection_prompt_module_members():
    module = _module_with()
    module.SOME_CONSTANT = "this causes confirms drives leads to outpaces"
    module.some_function = lambda: None
    validate_subsection_prompts(module)  # only SubsectionPrompt instances are scanned


def test_banned_term_lists_are_nonempty_and_disjoint():
    assert CC001_BANNED_TERMS and CC003_BANNED_TERMS
    assert not set(CC001_BANNED_TERMS) & set(CC003_BANNED_TERMS)
