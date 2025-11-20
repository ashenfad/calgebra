
import random
import pytest
from datetime import datetime, timedelta, timezone
from dateutil.rrule import rrule, DAILY, WEEKLY, MONTHLY, YEARLY, MO
from calgebra import recurring, DAY
from calgebra.interval import Interval

WEEK = 7 * DAY

# Constants
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
EPOCH_MONDAY = datetime(1969, 12, 29, tzinfo=timezone.utc)

def get_ground_truth(freq_str, interval, start_ts, end_ts, duration):
    """
    Generate ground truth intervals using rrule from Epoch.
    """
    if freq_str == "daily":
        freq = DAILY
        dtstart = EPOCH
    elif freq_str == "weekly":
        freq = WEEKLY
        dtstart = EPOCH_MONDAY
    elif freq_str == "monthly":
        freq = MONTHLY
        dtstart = EPOCH
    elif freq_str == "yearly":
        freq = YEARLY
        dtstart = EPOCH
    else:
        raise ValueError(f"Unknown freq: {freq_str}")

    # Create rrule
    # We use a simple rrule without byweekday/etc for the basic fuzz test
    # to focus on the phase/anchor logic.
    # If we want to test complex patterns, we'd need to mirror that in SUT.
    # For now, let's test the core "interval > 1" phase logic.
    rules = rrule(freq, interval=interval, dtstart=dtstart)
    
    # Convert query bounds to datetime for filtering
    # Note: rrule yields datetimes. We need to check overlaps.
    
    # Optimization: We can use rrule.between if we are careful about overlaps.
    # But to be safe and match the "infinite stream" concept, let's just
    # find the first one before start and iterate.
    
    # We need to catch events that start before 'start_ts' but end after it.
    # Max lookback needed is interval * freq_len + duration.
    # But since we start from Epoch, we can just iterate forward.
    # To avoid iterating from 1970 every time, we can use `after` to jump close.
    
    # Jump to just before query start
    # We want the occurrence just before (start_ts - duration) to be safe
    safe_start_dt = datetime.fromtimestamp(start_ts - duration, tz=timezone.utc)
    
    # rrule.between is exclusive of start? inclusive?
    # inc=True means inclusive.
    # We'll get a slice that definitely covers the window.
    query_end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    
    # Get candidates
    candidates = rules.between(safe_start_dt, query_end_dt, inc=True)
    
    # Also check one before safe_start_dt just in case (for long durations)
    before = rules.before(safe_start_dt, inc=False)
    if before:
        candidates.insert(0, before)
        
    results = []
    for dt in candidates:
        # Convert to Interval
        start = int(dt.timestamp())
        end = start + duration - 1
        
        # Check overlap with [start_ts, end_ts)
        # Interval is [start, end]
        # Query is [start_ts, end_ts) (exclusive end for fetch logic? 
        # Wait, fetch takes inclusive end in my implementation now?
        # No, fetch takes 'end' which is the last valid second.
        # But the test caller usually passes slice bounds.
        # Let's assume we are testing recurring(...)[start:end]
        # So we want intervals that overlap [start_ts, end_ts - 1]
        
        # Overlap logic:
        # max(start, start_ts) <= min(end, end_ts - 1)
        
        overlap_start = max(start, start_ts)
        overlap_end = min(end, end_ts - 1)
        
        if overlap_start <= overlap_end:
            results.append(Interval(start=overlap_start, end=overlap_end))
            
    # Flatten results to match recurring() behavior (which merges adjacent/overlapping)
    if not results:
        return []
        
    results.sort(key=lambda x: x.start)
    merged = []
    current = results[0]
    
    for next_ivl in results[1:]:
        # Merge if overlap or adjacent (end + 1 >= start)
        if current.end + 1 >= next_ivl.start:
            current = Interval(start=current.start, end=max(current.end, next_ivl.end))
        else:
            merged.append(current)
            current = next_ivl
    merged.append(current)
            
    return merged

@pytest.mark.parametrize("execution_number", range(50))
def test_fuzz_recurrence_phase(execution_number):
    """
    Fuzz test to verify recurrence phase logic against ground truth.
    """
    random.seed(execution_number)
    # Random parameters
    freq = random.choice(["daily", "weekly", "monthly", "yearly"])
    interval = random.randint(1, 5)
    duration = random.randint(1, 24) * 3600 # 1 hour to 1 day
    
    # Random query window in recent times (2020-2030)
    base_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    range_span = 10 * 365 * 24 * 3600
    
    query_start = base_ts + random.randint(0, range_span)
    # Query length: 1 day to 100 days
    query_len = random.randint(DAY, 100 * DAY)
    query_end = query_start + query_len
    
    # System Under Test
    # Note: We use default start=0 (midnight) to match ground truth rrule defaults
    timeline = recurring(freq=freq, interval=interval, duration=duration, tz="UTC")
    
    # Fetch
    # recurring()[start:end] returns intervals overlapping [start, end)
    actual = list(timeline[query_start:query_end])
    
    # Ground Truth
    expected = get_ground_truth(freq, interval, query_start, query_end, duration)
    
    # Compare
    # We only care about start times for equality checking usually, 
    # but let's check full intervals.
    
    # Debug info
    if actual != expected:
        print(f"\nFAILURE Params:")
        print(f"  Freq: {freq}")
        print(f"  Interval: {interval}")
        print(f"  Duration: {duration}")
        print(f"  Query: {query_start} to {query_end}")
        print(f"  Query DT: {datetime.fromtimestamp(query_start, tz=timezone.utc)} to {datetime.fromtimestamp(query_end, tz=timezone.utc)}")
        
        print(f"\nExpected ({len(expected)}):")
        for ivl in expected:
            print(f"  {datetime.fromtimestamp(ivl.start, tz=timezone.utc)} ({ivl.start})")
            
        print(f"\nActual ({len(actual)}):")
        for ivl in actual:
            print(f"  {datetime.fromtimestamp(ivl.start, tz=timezone.utc)} ({ivl.start})")
            
    assert actual == expected
