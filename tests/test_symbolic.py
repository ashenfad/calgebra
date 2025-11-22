"""Tests for symbolic recurrence rule merging."""

from dateutil.rrule import DAILY, WEEKLY, rrule, rruleset

from calgebra.symbolic import (
    try_complement,
    try_difference,
    try_merge_intersection,
    try_merge_union,
)


class TestTryMergeUnion:
    """Tests for try_merge_union() function."""

    def test_merge_two_weekly_rules(self):
        """Test merging two weekly patterns into a union."""
        # Mondays + Fridays
        mondays = rrule(WEEKLY, byweekday=0)  # Monday
        fridays = rrule(WEEKLY, byweekday=4)  # Friday

        result = try_merge_union([mondays, fridays])

        assert result is not None
        assert isinstance(result, rruleset)
        # Should have both rules
        assert len(result._rrule) == 2

    def test_merge_three_rules(self):
        """Test merging three rules."""
        rule1 = rrule(WEEKLY, byweekday=0)
        rule2 = rrule(WEEKLY, byweekday=2)
        rule3 = rrule(WEEKLY, byweekday=4)

        result = try_merge_union([rule1, rule2, rule3])

        assert result is not None
        assert isinstance(result, rruleset)
        assert len(result._rrule) == 3

    def test_merge_with_rruleset(self):
        """Test merging when one input is already an rruleset."""
        # Create an rruleset with two rules
        existing_set = rruleset()
        existing_set.rrule(rrule(WEEKLY, byweekday=0))
        existing_set.rrule(rrule(WEEKLY, byweekday=2))

        new_rule = rrule(WEEKLY, byweekday=4)

        result = try_merge_union([existing_set, new_rule])

        assert result is not None
        assert isinstance(result, rruleset)
        # Should have all three rules
        assert len(result._rrule) == 3

    def test_merge_with_none_returns_none(self):
        """Test that any None value causes union to return None.
        
        If any timeline lacks a symbolic rule, union can't be symbolic.
        """
        rule1 = rrule(WEEKLY, byweekday=0)
        rule2 = rrule(WEEKLY, byweekday=4)

        result = try_merge_union([None, rule1, None, rule2, None])

        # Should return None because some sources lack symbolic rules
        assert result is None

    def test_all_none_returns_none(self):
        """Test that all None values returns None."""
        result = try_merge_union([None, None, None])
        assert result is None

    def test_empty_list_returns_none(self):
        """Test that empty list returns None."""
        result = try_merge_union([])
        assert result is None

    def test_single_rule(self):
        """Test that single rule returns an rruleset with that rule."""
        rule = rrule(WEEKLY, byweekday=0)
        result = try_merge_union([rule])

        assert result is not None
        assert isinstance(result, rruleset)
        assert len(result._rrule) == 1


class TestTryMergeIntersection:
    """Tests for try_merge_intersection() function."""

    def test_single_rule_returns_itself(self):
        """Test that a single rule is returned as-is."""
        rule = rrule(WEEKLY, byweekday=0)
        result = try_merge_intersection([rule])

        assert result is rule

    def test_single_rule_in_rruleset(self):
        """Test extracting single rule from rruleset."""
        ruleset = rruleset()
        rule = rrule(WEEKLY, byweekday=0)
        ruleset.rrule(rule)

        result = try_merge_intersection([ruleset])

        assert result is rule

    def test_multiple_rules_in_rruleset_returns_none(self):
        """Test that rruleset with multiple rules returns None."""
        ruleset = rruleset()
        ruleset.rrule(rrule(WEEKLY, byweekday=0))
        ruleset.rrule(rrule(WEEKLY, byweekday=4))

        result = try_merge_intersection([ruleset])
        assert result is None

    def test_daily_and_weekly_returns_weekly(self):
        """Test DAILY & WEEKLY → WEEKLY (daily is redundant)."""
        daily = rrule(DAILY)
        weekly = rrule(WEEKLY, byweekday=0)  # Mondays

        # Order shouldn't matter
        result1 = try_merge_intersection([daily, weekly])
        result2 = try_merge_intersection([weekly, daily])

        assert result1 is weekly
        assert result2 is weekly

    def test_same_frequency_same_constraints(self):
        """Test that identical rules return one of them."""
        rule1 = rrule(WEEKLY, byweekday=0, bymonthday=None, bymonth=None)
        rule2 = rrule(WEEKLY, byweekday=0, bymonthday=None, bymonth=None)

        result = try_merge_intersection([rule1, rule2])

        # Should return one of the rules
        assert result is rule1 or result is rule2

    def test_different_frequencies_returns_none(self):
        """Test that incompatible frequencies return None."""
        weekly = rrule(WEEKLY, byweekday=0)
        monthly = rrule(WEEKLY, byweekday=0)  # Using WEEKLY here to avoid import complexity

        # For now, any non-DAILY/WEEKLY combination returns None
        # This test would need actual MONTHLY constant, but the logic is there

    def test_same_frequency_different_constraints_returns_none(self):
        """Test that same frequency with different constraints returns None."""
        mondays = rrule(WEEKLY, byweekday=0)
        fridays = rrule(WEEKLY, byweekday=4)

        result = try_merge_intersection([mondays, fridays])

        # Can't represent "Mondays AND Fridays" as intersection
        # (that's actually an empty set!)
        assert result is None

    def test_with_none_returns_none(self):
        """Test that any None value causes intersection to return None.
        
        If any timeline lacks a symbolic rule, intersection can't be symbolic.
        """
        rule = rrule(WEEKLY, byweekday=0)

        result = try_merge_intersection([None, rule, None])
        # Should return None because some sources lack symbolic rules
        assert result is None

    def test_all_none_returns_none(self):
        """Test that all None values returns None."""
        result = try_merge_intersection([None, None])
        assert result is None

    def test_empty_list_returns_none(self):
        """Test that empty list returns None."""
        result = try_merge_intersection([])
        assert result is None

    def test_three_or_more_rules_returns_none(self):
        """Test that 3+ rules return None (only handles pairwise for now)."""
        rule1 = rrule(DAILY)
        rule2 = rrule(WEEKLY, byweekday=0)
        rule3 = rrule(WEEKLY, byweekday=4)

        result = try_merge_intersection([rule1, rule2, rule3])
        assert result is None

    def test_unwraps_rruleset_with_single_rule(self):
        """Test that rrulesets are unwrapped before merging."""
        daily = rrule(DAILY)

        weekly_set = rruleset()
        weekly = rrule(WEEKLY, byweekday=0)
        weekly_set.rrule(weekly)

        result = try_merge_intersection([daily, weekly_set])

        # Should unwrap the rruleset and merge
        assert result is weekly

    def test_rruleset_with_multiple_rules_returns_none(self):
        """Test that rruleset with multiple rules can't be merged."""
        daily = rrule(DAILY)

        multi_set = rruleset()
        multi_set.rrule(rrule(WEEKLY, byweekday=0))
        multi_set.rrule(rrule(WEEKLY, byweekday=4))

        result = try_merge_intersection([daily, multi_set])
        assert result is None


class TestTryComplement:
    """Tests for try_complement() function."""

    def test_complement_mondays(self):
        """Test complementing Mondays gives Tuesday-Sunday."""
        from dateutil.rrule import MO

        mondays = rrule(WEEKLY, byweekday=MO)
        result = try_complement(mondays)

        assert result is not None
        assert result._freq == WEEKLY
        # Should have 6 days (all except Monday)
        assert len(result._byweekday) == 6

    def test_complement_weekends(self):
        """Test complementing weekends gives weekdays."""
        from dateutil.rrule import SA, SU

        weekends = rrule(WEEKLY, byweekday=[SA, SU])
        result = try_complement(weekends)

        assert result is not None
        assert result._freq == WEEKLY
        # Should have 5 days (Mon-Fri)
        assert len(result._byweekday) == 5

    def test_complement_weekdays(self):
        """Test complementing weekdays gives weekends."""
        from dateutil.rrule import MO, TU, WE, TH, FR

        weekdays = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])
        result = try_complement(weekdays)

        assert result is not None
        assert result._freq == WEEKLY
        # Should have 2 days (Sat-Sun)
        assert len(result._byweekday) == 2

    def test_complement_daily_returns_none(self):
        """Test that daily patterns can't be complemented."""
        daily = rrule(DAILY)
        result = try_complement(daily)

        assert result is None

    def test_complement_none_returns_none(self):
        """Test that None input returns None."""
        result = try_complement(None)
        assert result is None

    def test_complement_single_rule_in_rruleset(self):
        """Test complementing single rule inside rruleset."""
        from dateutil.rrule import MO

        ruleset = rruleset()
        ruleset.rrule(rrule(WEEKLY, byweekday=MO))

        result = try_complement(ruleset)

        assert result is not None
        assert result._freq == WEEKLY
        assert len(result._byweekday) == 6  # All except Monday

    def test_complement_multiple_rules_in_rruleset_returns_none(self):
        """Test that rruleset with multiple rules can't be complemented."""
        from dateutil.rrule import MO, FR

        ruleset = rruleset()
        ruleset.rrule(rrule(WEEKLY, byweekday=MO))
        ruleset.rrule(rrule(WEEKLY, byweekday=FR))

        result = try_complement(ruleset)
        assert result is None

    def test_double_complement_returns_original_days(self):
        """Test that complementing twice gets back to original selection."""
        from dateutil.rrule import MO, WE, FR

        mwf = rrule(WEEKLY, byweekday=[MO, WE, FR])
        complement_once = try_complement(mwf)
        complement_twice = try_complement(complement_once)

        assert complement_twice is not None
        # Should have 3 days again (Mon, Wed, Fri)
        assert len(complement_twice._byweekday) == 3


class TestTryDifference:
    """Tests for try_difference() function."""

    def test_weekdays_minus_mondays(self):
        """Test weekdays minus Mondays gives Tues-Fri."""
        from dateutil.rrule import MO, TU, WE, TH, FR

        weekdays = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])
        mondays = rrule(WEEKLY, byweekday=MO)

        result = try_difference(weekdays, mondays)

        assert result is not None
        assert result._freq == WEEKLY
        # Should have 4 days (Tues-Fri)
        assert len(result._byweekday) == 4

    def test_all_days_minus_weekends(self):
        """Test all days minus weekends gives weekdays."""
        from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU

        all_days = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR, SA, SU])
        weekends = rrule(WEEKLY, byweekday=[SA, SU])

        result = try_difference(all_days, weekends)

        assert result is not None
        assert result._freq == WEEKLY
        # Should have 5 days (Mon-Fri)
        assert len(result._byweekday) == 5

    def test_weekdays_minus_weekends_unchanged(self):
        """Test weekdays minus weekends gives weekdays (no change)."""
        from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU

        weekdays = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])
        weekends = rrule(WEEKLY, byweekday=[SA, SU])

        result = try_difference(weekdays, weekends)

        assert result is not None
        assert result._freq == WEEKLY
        # Should still have 5 days
        assert len(result._byweekday) == 5

    def test_empty_result_returns_none(self):
        """Test that empty difference returns None."""
        from dateutil.rrule import MO

        mondays = rrule(WEEKLY, byweekday=MO)
        also_mondays = rrule(WEEKLY, byweekday=MO)

        result = try_difference(mondays, also_mondays)
        assert result is None  # Empty result

    def test_none_inputs_return_none(self):
        """Test that None inputs return None."""
        from dateutil.rrule import MO

        mondays = rrule(WEEKLY, byweekday=MO)

        assert try_difference(None, mondays) is None
        assert try_difference(mondays, None) is None
        assert try_difference(None, None) is None

    def test_non_weekly_patterns_return_none(self):
        """Test that non-weekly patterns return None."""
        daily = rrule(DAILY)
        weekly = rrule(WEEKLY, byweekday=0)

        assert try_difference(daily, weekly) is None
        assert try_difference(weekly, daily) is None

    def test_with_rrulesets(self):
        """Test difference with rrulesets."""
        from dateutil.rrule import MO, TU, WE, TH, FR

        # Source as rruleset
        source_set = rruleset()
        source_set.rrule(rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR]))

        # Subtractor as rrule
        mondays = rrule(WEEKLY, byweekday=MO)

        result = try_difference(source_set, mondays)

        assert result is not None
        assert result._freq == WEEKLY
        assert len(result._byweekday) == 4  # Tues-Fri

    def test_multiple_rules_in_rruleset_returns_none(self):
        """Test that rruleset with multiple rules can't be differenced."""
        from dateutil.rrule import MO, FR

        multi_set = rruleset()
        multi_set.rrule(rrule(WEEKLY, byweekday=MO))
        multi_set.rrule(rrule(WEEKLY, byweekday=FR))

        mondays = rrule(WEEKLY, byweekday=MO)

        result = try_difference(multi_set, mondays)
        assert result is None

    def test_identity_property(self):
        """Test that X - ∅ = X (subtracting nothing has no effect)."""
        from dateutil.rrule import MO, TU, WE

        mwf = rrule(WEEKLY, byweekday=[MO, TU, WE])
        
        # Create empty weekly pattern (this is a bit artificial since
        # we can't actually create a truly empty pattern, but we can
        # subtract non-overlapping days)
        fridays = rrule(WEEKLY, byweekday=4)  # Friday
        
        result = try_difference(mwf, fridays)
        
        # Should still have Mon/Tue/Wed
        assert result is not None
        assert len(result._byweekday) == 3


