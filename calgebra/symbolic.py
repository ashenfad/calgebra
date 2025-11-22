"""Symbolic recurrence rule merging utilities.

This module provides best-effort merging of RFC 5545 recurrence rules for
Union and Intersection operations. It has no dependencies on other calgebra
modules to avoid circular imports.

The functions in this module attempt to combine recurrence rules symbolically
when possible, falling back to None when the combination cannot be represented
as an RFC 5545 rule.
"""

from dateutil.rrule import rrule, rruleset


def try_merge_union(rules: list[rrule | rruleset | None]) -> rruleset | None:
    """Combine multiple recurrence rules into a union rruleset.

    This is straightforward - rruleset natively supports multiple rrules,
    so we can always merge them symbolically.

    Args:
        rules: List of recurrence rules (rrule or rruleset objects), may contain None

    Returns:
        Combined rruleset, or None if all input rules are None

    Examples:
        # Combine weekly Monday + weekly Friday = Mon/Fri pattern
        mondays = rrule(WEEKLY, byweekday=MO)
        fridays = rrule(WEEKLY, byweekday=FR)
        combined = try_merge_union([mondays, fridays])
    """
    # If any timeline lacks a symbolic rule, union can't be symbolic
    if any(r is None for r in rules):
        return None

    if not rules:
        return None

    # Create a new rruleset and add all rules
    result = rruleset()

    for rule in rules:
        if isinstance(rule, rruleset):
            # If it's already an rruleset, add all its rrules
            for rrule_item in rule._rrule:  # Access internal _rrule list
                result.rrule(rrule_item)
        else:
            # Single rrule
            result.rrule(rule)

    return result


def try_merge_intersection(rules: list[rrule | rruleset | None]) -> rrule | None:
    """Attempt to merge recurrence rules for intersection (best-effort).

    Intersection of recurrence rules is only representable in RFC 5545 for
    specific cases. This function handles common patterns and returns None
    when the intersection cannot be represented symbolically.

    Common representable cases:
    - Daily + weekly (specific day) → weekly on that day
    - Weekly (any day) + time window → weekly on that day with time window
    - Monthly + day of week → monthly on specific weekday

    Args:
        rules: List of recurrence rules to intersect

    Returns:
        Merged rrule if representable, None otherwise

    Examples:
        # Daily pattern intersected with "only Mondays"
        daily = rrule(DAILY)
        mondays = rrule(WEEKLY, byweekday=MO)
        result = try_merge_intersection([daily, mondays])
        # Returns: rrule(WEEKLY, byweekday=MO)

    Note:
        This is a best-effort implementation. Many intersections cannot be
        represented as a single rrule and will return None, causing the
        timeline to fall back to scanning.
    """
    # If any timeline lacks a symbolic rule, intersection can't be symbolic
    if any(r is None for r in rules):
        return None

    if not rules:
        return None

    if len(rules) == 1:
        # Single rule - just return it (or extract from rruleset)
        rule = rules[0]
        if isinstance(rule, rruleset):
            # If it's an rruleset with a single rrule, extract it
            if len(rule._rrule) == 1:
                return rule._rrule[0]
            else:
                # Multiple rrules in set - can't represent as single rrule
                return None
        return rule

    # Multiple rules - attempt to merge common patterns
    # Convert rrulesets to individual rrules if possible
    unwrapped_rules = []
    for rule in rules:
        if isinstance(rule, rruleset):
            if len(rule._rrule) == 1:
                unwrapped_rules.append(rule._rrule[0])
            else:
                # Can't merge rruleset with multiple rules
                return None
        else:
            unwrapped_rules.append(rule)

    if len(unwrapped_rules) != 2:
        # Only handle 2-way intersections for now
        return None

    rule1, rule2 = unwrapped_rules

    # Pattern 1: DAILY & WEEKLY(byweekday=X) → WEEKLY(byweekday=X)
    # The daily pattern is redundant when intersected with weekly
    from dateutil.rrule import DAILY, WEEKLY

    if rule1._freq == DAILY and rule2._freq == WEEKLY:
        # Daily is subsumed by weekly constraint
        return rule2
    elif rule2._freq == DAILY and rule1._freq == WEEKLY:
        # Daily is subsumed by weekly constraint
        return rule1

    # Pattern 2: Same frequency, try to merge constraints
    # This handles cases like two DAILY patterns with different time windows
    if rule1._freq == rule2._freq:
        # For same-frequency rules, we can potentially merge them
        # by combining their constraints (byweekday, bymonthday, etc.)
        # However, this is complex and depends on the specific constraints
        # For now, we only handle the case where one rule is a subset of the other

        # If rules are identical or very similar, return one of them
        # This is conservative but safe
        if (
            rule1._freq == rule2._freq
            and rule1._byweekday == rule2._byweekday
            and rule1._bymonthday == rule2._bymonthday
            and rule1._bymonth == rule2._bymonth
        ):
            # Same constraints - they're equivalent
            return rule1

    # No pattern matched - can't represent symbolically
    return None


def try_complement(rule: rrule | rruleset | None) -> rrule | None:
    """Attempt to complement a recurrence rule (best-effort).

    Only works for weekly patterns where we can invert the day selection.
    Other patterns return None and fall back to scanning.

    Args:
        rule: The recurrence rule to complement

    Returns:
        Complemented rrule if representable, None otherwise

    Examples:
        # Complement of Mondays = Tuesday through Sunday
        mondays = rrule(WEEKLY, byweekday=MO)
        complement = try_complement(mondays)
        # Returns: rrule(WEEKLY, byweekday=[TU, WE, TH, FR, SA, SU])

        # Complement of weekends = weekdays
        weekends = rrule(WEEKLY, byweekday=[SA, SU])
        complement = try_complement(weekends)
        # Returns: rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])

    Note:
        Only supports weekly patterns. Daily, monthly, yearly patterns
        cannot be meaningfully complemented in RFC 5545.
    """
    if rule is None:
        return None

    # Extract single rrule if wrapped in rruleset
    if isinstance(rule, rruleset):
        if len(rule._rrule) == 1:
            rule = rule._rrule[0]
        else:
            # Can't complement rruleset with multiple rules
            return None

    from dateutil.rrule import WEEKLY

    # Only support weekly patterns
    if rule._freq != WEEKLY:
        return None

    # Get selected days (None means all days, which we can't complement)
    if rule._byweekday is None:
        return None  # Complement of "every day" is empty set

    # Convert to set of day indices
    selected_days = set()
    for day in rule._byweekday:
        # dateutil weekday objects have .weekday attribute
        if hasattr(day, 'weekday'):
            selected_days.add(day.weekday)
        else:
            # Already an integer
            selected_days.add(day)

    # Complement: all days except selected
    all_days = {0, 1, 2, 3, 4, 5, 6}  # Monday=0 through Sunday=6
    complement_days = all_days - selected_days

    if not complement_days:
        return None  # Complement is empty

    # Create new rule with complemented days
    # Convert back to dateutil weekday objects
    from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU
    weekday_map = {0: MO, 1: TU, 2: WE, 3: TH, 4: FR, 5: SA, 6: SU}
    complement_weekdays = [weekday_map[day] for day in sorted(complement_days)]

    return rrule(WEEKLY, byweekday=complement_weekdays)


def try_difference(
    rule1: rrule | rruleset | None, rule2: rrule | rruleset | None
) -> rrule | None:
    """Attempt to compute difference of two recurrence rules (best-effort).

    Only works for weekly patterns where we can subtract day selections.
    Other patterns return None and fall back to scanning.

    Args:
        rule1: The source recurrence rule
        rule2: The rule to subtract from rule1

    Returns:
        Difference rrule if representable, None otherwise

    Examples:
        # Weekdays minus Mondays = Tues-Fri
        weekdays = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])
        mondays = rrule(WEEKLY, byweekday=MO)
        result = try_difference(weekdays, mondays)
        # Returns: rrule(WEEKLY, byweekday=[TU, WE, TH, FR])

        # All days minus weekends = weekdays
        all_days = rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR, SA, SU])
        weekends = rrule(WEEKLY, byweekday=[SA, SU])
        result = try_difference(all_days, weekends)
        # Returns: rrule(WEEKLY, byweekday=[MO, TU, WE, TH, FR])

    Note:
        Only supports weekly patterns. Daily, monthly, yearly patterns
        cannot be meaningfully differenced in RFC 5545.
    """
    if rule1 is None or rule2 is None:
        return None

    # Extract single rrules if wrapped in rrulesets
    if isinstance(rule1, rruleset):
        if len(rule1._rrule) == 1:
            rule1 = rule1._rrule[0]
        else:
            return None

    if isinstance(rule2, rruleset):
        if len(rule2._rrule) == 1:
            rule2 = rule2._rrule[0]
        else:
            return None

    from dateutil.rrule import WEEKLY

    # Only support weekly patterns
    if rule1._freq != WEEKLY or rule2._freq != WEEKLY:
        return None

    # Get selected days
    if rule1._byweekday is None or rule2._byweekday is None:
        return None

    # Convert to sets of day indices
    def extract_days(weekdays):
        days = set()
        for day in weekdays:
            if hasattr(day, 'weekday'):
                days.add(day.weekday)
            else:
                days.add(day)
        return days

    days1 = extract_days(rule1._byweekday)
    days2 = extract_days(rule2._byweekday)

    # Compute difference: days in rule1 but not in rule2
    result_days = days1 - days2

    if not result_days:
        return None  # Empty result

    # Create new rule with difference days
    from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU
    weekday_map = {0: MO, 1: TU, 2: WE, 3: TH, 4: FR, 5: SA, 6: SU}
    result_weekdays = [weekday_map[day] for day in sorted(result_days)]

    return rrule(WEEKLY, byweekday=result_weekdays)


