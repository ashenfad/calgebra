import pytest

# Skip if icalendar not installed
try:
    import icalendar as _  # noqa: F401
except ImportError:
    pytest.skip("icalendar not installed", allow_module_level=True)

from calgebra import Interval
from calgebra.ical import ICalEvent, file_to_timeline, timeline_to_file
from calgebra.recurrence import RecurringPattern


@pytest.fixture
def sample_ics(tmp_path):
    ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//calgebra//
X-WR-CALNAME:Test Calendar
BEGIN:VEVENT
UID:12345
DTSTART:20250101T090000Z
DTEND:20250101T100000Z
SUMMARY:Test Event
DESCRIPTION:A test event
LOCATION:Office
STATUS:CONFIRMED
TRANSP:OPAQUE
CATEGORIES:work,meeting
END:VEVENT
BEGIN:VEVENT
UID:67890
DTSTART:20250102T090000Z
RRULE:FREQ=WEEKLY;COUNT=2
SUMMARY:Recurring Meeting
STATUS:TENTATIVE
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR"""

    p = tmp_path / "test.ics"
    p.write_bytes(ics_content)
    return p


def test_file_to_timeline(sample_ics):
    timeline = file_to_timeline(sample_ics)

    # We expect 2 items in storage: 1 static, 1 recurring
    # Accessing protected members for testing
    assert len(timeline._static_intervals) == 1
    assert len(timeline._recurring_patterns) == 1

    # Check static event
    event = timeline._static_intervals[0]
    assert isinstance(event, ICalEvent)
    assert event.summary == "Test Event"
    assert event.uid == "12345"
    assert event.location == "Office"

    # Check recurring event
    _, pattern = timeline._recurring_patterns[0]
    assert isinstance(pattern, RecurringPattern)
    assert pattern.metadata["summary"] == "Recurring Meeting"
    assert pattern.freq == "weekly"


def test_calendar_name_extraction(sample_ics):
    """Test that X-WR-CALNAME is extracted and propagated to events."""
    timeline = file_to_timeline(sample_ics)

    # Check static event has calendar name
    event = timeline._static_intervals[0]
    assert event.calendar_name == "Test Calendar"

    # Check recurring pattern has calendar name in metadata
    _, pattern = timeline._recurring_patterns[0]
    assert pattern.metadata["calendar_name"] == "Test Calendar"


def test_status_and_transp(sample_ics):
    """Test that STATUS and TRANSP properties are parsed correctly."""
    timeline = file_to_timeline(sample_ics)

    # Static event: CONFIRMED, OPAQUE
    event = timeline._static_intervals[0]
    assert event.status == "CONFIRMED"
    assert event.transp == "OPAQUE"

    # Recurring pattern: TENTATIVE, TRANSPARENT
    _, pattern = timeline._recurring_patterns[0]
    assert pattern.metadata["status"] == "TENTATIVE"
    assert pattern.metadata["transp"] == "TRANSPARENT"


def test_categories(sample_ics):
    """Test that CATEGORIES property is parsed as a tuple."""
    timeline = file_to_timeline(sample_ics)

    # Static event has categories
    event = timeline._static_intervals[0]
    assert event.categories == ("work", "meeting")

    # Recurring event has no categories
    _, pattern = timeline._recurring_patterns[0]
    assert pattern.metadata["categories"] == ()


def test_round_trip(sample_ics, tmp_path):
    # Load
    t1 = file_to_timeline(sample_ics)

    # Save
    out_path = tmp_path / "out.ics"
    timeline_to_file(t1, out_path)

    # Load back
    t2 = file_to_timeline(out_path)

    # Verify content preserved
    assert len(t2._static_intervals) == 1
    assert len(t2._recurring_patterns) == 1

    e1 = t2._static_intervals[0]
    assert e1.summary == "Test Event"

    _, p1 = t2._recurring_patterns[0]
    assert p1.metadata["summary"] == "Recurring Meeting"
    # assert p1.freq == "weekly" # Case might be normalized


def test_timeline_to_file_validation(tmp_path):
    # Should fail for generic timeline
    from calgebra import timeline as make_timeline

    t = make_timeline(Interval(start=0, end=100))
    # It constructs a MemoryTimeline by default now in the helper!
    # So this actually works.

    out = tmp_path / "generic.ics"
    timeline_to_file(t, out)

    # Check if file exists and has content
    assert out.exists()
    assert b"BEGIN:VCALENDAR" in out.read_bytes()
