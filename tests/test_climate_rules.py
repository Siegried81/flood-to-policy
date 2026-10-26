"""The two climate reading rules the UIs share: which sign column, which spread.

Both were redefined when the ensemble grew from two chains to sixteen; what is
pinned here is that each rule still gives the two-chain answer at two members.
"""

from __future__ import annotations

import pandas as pd

from api.main import climate_periods, sign_column, with_size_uncertain


def _table(members, low, high, p25, p75):
    return pd.DataFrame({
        "nuts_id": ["A"],
        "ensemble_members_2041_2070": [members],
        "change_pct_ensemble_median_2041_2070": [20.0],
        "change_pct_ensemble_min_2041_2070": [low],
        "change_pct_ensemble_max_2041_2070": [high],
        "change_pct_ensemble_p25_2041_2070": [p25],
        "change_pct_ensemble_p75_2041_2070": [p75],
        "ensemble_agrees_on_sign_2041_2070": [False],
        "ensemble_robust_on_sign_2041_2070": [True],
    })


def test_sixteen_members_are_judged_on_the_interquartile_range():
    """One extreme model 300 points out must not unrank a region whose middle
    half of members sits 20 points apart."""
    flagged = with_size_uncertain(_table(16, -50.0, 300.0, 10.0, 30.0))
    assert not bool(flagged["ensemble_size_uncertain_2041_2070"].iat[0])


def test_sixteen_members_far_apart_in_the_middle_are_still_flagged():
    flagged = with_size_uncertain(_table(16, -50.0, 300.0, 0.0, 150.0))
    assert bool(flagged["ensemble_size_uncertain_2041_2070"].iat[0])


def test_two_members_keep_the_full_range():
    """At two members the quartiles sit inside the range and would hide the
    +92% / +414% split the flag was written for."""
    flagged = with_size_uncertain(_table(2, 92.0, 414.0, 172.5, 333.5))
    assert bool(flagged["ensemble_size_uncertain_2041_2070"].iat[0])


def test_the_robust_column_is_read_when_the_table_has_it():
    column, wording = sign_column(_table(16, 0, 1, 0, 1), "2041_2070")
    assert column == "ensemble_robust_on_sign_2041_2070" and "80 %" in wording
    older = _table(2, 0, 1, 0, 1).drop(columns="ensemble_robust_on_sign_2041_2070")
    assert sign_column(older, "2041_2070")[0] == "ensemble_agrees_on_sign_2041_2070"


def test_the_period_summary_reports_both_counts():
    summary = climate_periods(_table(16, -50.0, 300.0, 10.0, 30.0))[0]
    assert summary["regions_robust_on_sign"] == 1
    assert summary["regions_agreeing_on_sign"] == 0
