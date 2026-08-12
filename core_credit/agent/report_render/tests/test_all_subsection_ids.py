from report_render.section_layout import ALL_SUBSECTION_IDS


def test_no_duplicate_ids():
    assert len(ALL_SUBSECTION_IDS) == len(set(ALL_SUBSECTION_IDS))


def test_matches_the_26_real_template_visual_slots():
    assert len(ALL_SUBSECTION_IDS) == 26
