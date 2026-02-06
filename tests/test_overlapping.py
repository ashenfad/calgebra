"""Tests for overlapping() on Difference and Complement timelines.

These test the overrides that fetch subtractors/source intervals across the
full range (not just [point, point+1)), fixing incorrect clipping behavior.
"""

from calgebra import Interval
from calgebra.mutable.memory import timeline

# --- Difference.overlapping ---


class TestDifferenceOverlapping:
    """Tests for Difference.overlapping() returning unclipped fragments."""

    def test_point_in_subtracted_region(self):
        """Point inside a subtracted hole returns nothing."""
        source = timeline(Interval(start=10, end=50))
        sub = timeline(Interval(start=20, end=30))
        diff = source - sub

        assert list(diff.overlapping(25)) == []

    def test_point_in_left_fragment(self):
        """Point in the fragment before the hole returns full fragment."""
        source = timeline(Interval(start=10, end=50))
        sub = timeline(Interval(start=20, end=30))
        diff = source - sub

        result = list(diff.overlapping(15))
        assert len(result) == 1
        assert result[0].start == 10
        assert result[0].end == 20

    def test_point_in_right_fragment(self):
        """Point in the fragment after the hole returns full fragment."""
        source = timeline(Interval(start=10, end=50))
        sub = timeline(Interval(start=20, end=30))
        diff = source - sub

        result = list(diff.overlapping(35))
        assert len(result) == 1
        assert result[0].start == 30
        assert result[0].end == 50

    def test_point_outside_source(self):
        """Point outside source returns nothing."""
        source = timeline(Interval(start=10, end=50))
        sub = timeline(Interval(start=20, end=30))
        diff = source - sub

        assert list(diff.overlapping(5)) == []
        assert list(diff.overlapping(55)) == []

    def test_multiple_holes(self):
        """Source with multiple holes returns correct fragment."""
        source = timeline(Interval(start=0, end=100))
        sub = timeline(
            Interval(start=20, end=30),
            Interval(start=50, end=60),
        )
        diff = source - sub

        # Middle fragment [30, 50)
        result = list(diff.overlapping(40))
        assert len(result) == 1
        assert result[0].start == 30
        assert result[0].end == 50

        # Last fragment [60, 100)
        result = list(diff.overlapping(80))
        assert len(result) == 1
        assert result[0].start == 60
        assert result[0].end == 100

    def test_no_subtractors(self):
        """Difference with no subtractors delegates to source."""
        source = timeline(Interval(start=10, end=50))
        diff = source - timeline()

        result = list(diff.overlapping(25))
        assert len(result) == 1
        assert result[0].start == 10
        assert result[0].end == 50

    def test_point_at_hole_boundary(self):
        """Point exactly at hole start or end."""
        source = timeline(Interval(start=0, end=100))
        sub = timeline(Interval(start=40, end=60))
        diff = source - sub

        # Point at hole start (40 is subtracted)
        assert list(diff.overlapping(40)) == []

        # Point at hole end (60 is in right fragment [60, 100))
        result = list(diff.overlapping(60))
        assert len(result) == 1
        assert result[0].start == 60
        assert result[0].end == 100

        # Point just before hole (39 is in left fragment [0, 40))
        result = list(diff.overlapping(39))
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == 40

    def test_double_difference(self):
        """Nested difference: (A - B) - C."""
        A = timeline(Interval(start=0, end=100))
        B = timeline(Interval(start=20, end=30))
        C = timeline(Interval(start=50, end=60))
        double_diff = (A - B) - C

        # In [0, 20)
        result = list(double_diff.overlapping(10))
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == 20

        # In first hole [20, 30) -> empty
        assert list(double_diff.overlapping(25)) == []

        # In [30, 50)
        result = list(double_diff.overlapping(40))
        assert len(result) == 1
        assert result[0].start == 30
        assert result[0].end == 50

        # In second hole [50, 60) -> empty
        assert list(double_diff.overlapping(55)) == []

        # In [60, 100)
        result = list(double_diff.overlapping(80))
        assert len(result) == 1
        assert result[0].start == 60
        assert result[0].end == 100

    def test_subtractor_wider_than_source(self):
        """Subtractor fully covers source."""
        source = timeline(Interval(start=20, end=30))
        sub = timeline(Interval(start=10, end=50))
        diff = source - sub

        assert list(diff.overlapping(25)) == []

    def test_multiple_source_intervals(self):
        """Multiple source intervals with shared subtractor."""
        source = timeline(
            Interval(start=0, end=20),
            Interval(start=30, end=50),
        )
        sub = timeline(Interval(start=10, end=40))
        diff = source - sub

        # First source fragment [0, 10)
        result = list(diff.overlapping(5))
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == 10

        # Second source fragment [40, 50)
        result = list(diff.overlapping(45))
        assert len(result) == 1
        assert result[0].start == 40
        assert result[0].end == 50


# --- Complement.overlapping ---


class TestComplementOverlapping:
    """Tests for Complement.overlapping() returning unclipped gaps."""

    def test_gap_between_intervals(self):
        """Point in a gap between source intervals."""
        source = timeline(
            Interval(start=10, end=20),
            Interval(start=30, end=40),
        )
        comp = ~source

        result = list(comp.overlapping(25))
        assert len(result) == 1
        assert result[0].start == 20
        assert result[0].end == 30

    def test_point_in_source(self):
        """Point inside a source interval returns nothing."""
        source = timeline(Interval(start=10, end=20))
        comp = ~source

        assert len(list(comp.overlapping(15))) == 0

    def test_gap_before_all_sources(self):
        """Point before all source intervals returns [None, first_start)."""
        source = timeline(Interval(start=10, end=20))
        comp = ~source

        result = list(comp.overlapping(5))
        assert len(result) == 1
        assert result[0].start is None
        assert result[0].end == 10

    def test_gap_after_all_sources(self):
        """Point after all source intervals returns [last_end, None)."""
        source = timeline(Interval(start=10, end=20))
        comp = ~source

        result = list(comp.overlapping(25))
        assert len(result) == 1
        assert result[0].start == 20
        assert result[0].end is None

    def test_empty_source(self):
        """Complement of empty timeline: entire real line."""
        comp = ~timeline()

        result = list(comp.overlapping(0))
        assert len(result) == 1
        assert result[0].start is None
        assert result[0].end is None

    def test_point_at_source_end_boundary(self):
        """Point exactly at the end of a source interval (exclusive)."""
        source = timeline(
            Interval(start=10, end=20),
            Interval(start=30, end=40),
        )
        comp = ~source

        # 20 is NOT in [10, 20) so it's in the gap [20, 30)
        result = list(comp.overlapping(20))
        assert len(result) == 1
        assert result[0].start == 20
        assert result[0].end == 30

    def test_point_at_source_start_boundary(self):
        """Point exactly at the start of a source interval (inclusive)."""
        source = timeline(Interval(start=10, end=20))
        comp = ~source

        # 10 IS in [10, 20)
        assert len(list(comp.overlapping(10))) == 0

    def test_multiple_gaps(self):
        """Multiple gaps, each queried independently."""
        source = timeline(
            Interval(start=10, end=20),
            Interval(start=30, end=40),
            Interval(start=50, end=60),
        )
        comp = ~source

        # Gap [20, 30)
        result = list(comp.overlapping(25))
        assert len(result) == 1
        assert result[0].start == 20
        assert result[0].end == 30

        # Gap [40, 50)
        result = list(comp.overlapping(45))
        assert len(result) == 1
        assert result[0].start == 40
        assert result[0].end == 50


# --- Complement of Difference (nested) ---


class TestComplementOfDifference:
    """Tests for ~(A - B), exercising both overrides together."""

    def test_complement_of_difference_finds_holes(self):
        """Holes carved by subtraction become complement intervals."""
        A = timeline(Interval(start=0, end=100))
        B = timeline(
            Interval(start=20, end=30),
            Interval(start=50, end=60),
        )
        comp_diff = ~(A - B)

        # Point in hole [20, 30) -> complement gap
        result = list(comp_diff.overlapping(25))
        assert len(result) == 1
        assert result[0].start == 20
        assert result[0].end == 30

        # Point in hole [50, 60) -> complement gap
        result = list(comp_diff.overlapping(55))
        assert len(result) == 1
        assert result[0].start == 50
        assert result[0].end == 60

    def test_complement_of_difference_in_surviving_fragment(self):
        """Point in a surviving fragment of A-B has no complement interval."""
        A = timeline(Interval(start=0, end=100))
        B = timeline(Interval(start=20, end=30))
        comp_diff = ~(A - B)

        # Point 10 is in A-B fragment [0, 20) -> not in complement
        assert len(list(comp_diff.overlapping(10))) == 0
        assert len(list(comp_diff.overlapping(50))) == 0

    def test_complement_of_difference_before_source(self):
        """Point before A -> gap from -inf to A's start."""
        A = timeline(Interval(start=100, end=200))
        B = timeline(Interval(start=120, end=130))
        comp_diff = ~(A - B)

        result = list(comp_diff.overlapping(50))
        assert len(result) == 1
        assert result[0].start is None
        assert result[0].end == 100

    def test_complement_of_difference_after_source(self):
        """Point after A -> gap from A's end to +inf."""
        A = timeline(Interval(start=0, end=100))
        B = timeline(Interval(start=20, end=30))
        comp_diff = ~(A - B)

        result = list(comp_diff.overlapping(150))
        assert len(result) == 1
        assert result[0].start == 100
        assert result[0].end is None


# --- Difference of Complement (nested) ---


class TestDifferenceOfComplement:
    """Tests for (~A) - B, exercising both overrides together."""

    def test_difference_of_complement(self):
        """Subtracting from complement narrows the gaps."""
        A = timeline(Interval(start=20, end=40))
        B = timeline(Interval(start=10, end=15))
        diff_comp = (~A) - B

        # Point 5 is in ~A and not in B -> gap fragment [None, 10)
        result = list(diff_comp.overlapping(5))
        assert len(result) == 1
        assert result[0].start is None
        assert result[0].end == 10

        # Point 12 is in ~A but also in B -> subtracted
        assert list(diff_comp.overlapping(12)) == []

        # Point 50 is in ~A and not in B -> gap [40, None)
        result = list(diff_comp.overlapping(50))
        assert len(result) == 1
        assert result[0].start == 40
        assert result[0].end is None
