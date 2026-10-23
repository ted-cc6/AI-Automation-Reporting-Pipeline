"""CC-035: the SubsectionPrompt banned-term guard. chain.py already runs validate_subsection_prompts()
against the real section_prompts module at import time -- these tests exercise the checker function
itself against synthetic modules, so a real violation is provable independent of the current (clean)
state of section_prompts.py.
"""
import types

import pytest

import re

from writer.causal_lint import HARD_TERMS
from writer.chain import SYSTEM_PROMPT, validate_subsection_prompts
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


def test_the_single_hard_list_keeps_every_old_cc001_cc003_term():
    # CC-083 retired chain.py's own lists in favour of causal_lint.HARD_TERMS. Nothing they
    # banned may silently drop out. "mechanism behind" is covered by "mechanism"; "ahead of" is
    # hard only against the benchmark, since plain "ahead of schooling" (cc066 4.1) is fine.
    old_cc001 = ("confirms", "drives", "translating into", "shifts", "proves", "causes", "payoff",
                 "evidence of", "demonstrates", "leads to", "leading to", "lead to", "should raise",
                 "will improve", "would remove", "leverage", "mechanism")
    old_cc003 = ("outpaces", "beats", "outperforms", "wins", "ahead of the mfi index")
    missing = [t for t in old_cc001 + old_cc003 if t not in HARD_TERMS]
    assert missing == []


@pytest.mark.parametrize(
    "instructions, term",
    [
        # Real prompt wording from before this round, each the source of a reviewed violation.
        ("Note where the client base is poorer, which shows stronger targeting of the poor.", "targeting of the poor"),  # 2.2 -> HO24
        ("Rank the top promoter drivers and the top detractor pain points.", "drivers"),  # 8.2 -> HO54
        ("Fold in the NPS and the top driver on each side.", "driver"),  # 8-insight
        ("Quantify those who did, a core over-indebtedness flag.", "over-indebtedness"),  # 5.5
    ],
)
def test_catches_the_prompt_wording_behind_this_rounds_violations(instructions, term):
    module = _module_with(BAD=SubsectionPrompt(subsection_id="x.1", title="A clean title", word_cap=80, instructions=instructions))
    with pytest.raises(ValueError, match=re.escape(term)):
        validate_subsection_prompts(module)


def test_a_quoted_or_negated_banned_example_is_allowed():
    module = _module_with(
        OK=SubsectionPrompt(
            subsection_id="x.1", title="A clean title", word_cap=80,
            instructions='A reviewer flagged "a strong competitive moat". On its own it does not establish misselling.',
        ),
    )
    validate_subsection_prompts(module)  # must not raise


def test_system_prompt_has_rules_r1_to_r8_each_with_a_replacement():
    # CC-076 to CC-083: every rule pairs a banned example with an approved replacement.
    for n in range(1, 9):
        start = SYSTEM_PROMPT.index(f"R{n} ")
        end = SYSTEM_PROMPT.index(f"R{n + 1} ") if n < 8 else SYSTEM_PROMPT.index("Do not assert that two figures")
        assert "Instead of" in SYSTEM_PROMPT[start:end], f"R{n} has no 'Instead of' replacement"
    assert "R9" not in SYSTEM_PROMPT  # CC-084 stays on hold until Henry confirms
