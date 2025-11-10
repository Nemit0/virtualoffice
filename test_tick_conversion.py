#!/usr/bin/env python3
"""
Test script to verify tick conversion utilities work correctly.
"""

import sys
sys.path.insert(0, 'src')

from virtualoffice.sim_manager.core.tick_manager import TickManager

def test_tick_conversions():
    """Test all tick conversion methods."""
    tm = TickManager()

    print("=" * 80)
    print("TICK CONVERSION UTILITY TESTS")
    print("=" * 80)

    # Test constants
    print(f"\nConstants:")
    print(f"  TICKS_PER_CALENDAR_DAY  = {tm.TICKS_PER_CALENDAR_DAY:,} ticks (24 hours)")
    print(f"  TICKS_PER_CALENDAR_WEEK = {tm.TICKS_PER_CALENDAR_WEEK:,} ticks (7 days)")

    # Test critical tick from our bug reports
    print("\n" + "=" * 80)
    print("CRITICAL TEST: Tick 10,286 (from bug report)")
    print("=" * 80)

    test_tick = 10286
    week = tm.tick_to_week(test_tick)
    day = tm.tick_to_day(test_tick)

    print(f"\nTick {test_tick:,}:")
    print(f"  Week: {week} (Expected: 2)")
    print(f"  Day:  {day} (Expected: 8)")
    print(f"  ✓ PASS" if week == 2 else f"  ✗ FAIL - Expected week 2, got {week}")

    # Test week boundaries
    print("\n" + "=" * 80)
    print("WEEK BOUNDARY TESTS")
    print("=" * 80)

    test_cases = [
        (1, 1, "First tick"),
        (10080, 1, "Last tick of week 1"),
        (10081, 2, "First tick of week 2"),
        (20160, 2, "Last tick of week 2"),
        (20161, 3, "First tick of week 3"),
        (30240, 3, "Last tick of week 3"),
        (30241, 4, "First tick of week 4"),
    ]

    all_passed = True
    for tick, expected_week, description in test_cases:
        week = tm.tick_to_week(tick)
        status = "✓" if week == expected_week else "✗"
        if week != expected_week:
            all_passed = False
        print(f"  {status} Tick {tick:6,}: Week {week} (expected {expected_week}) - {description}")

    # Test day boundaries
    print("\n" + "=" * 80)
    print("DAY BOUNDARY TESTS")
    print("=" * 80)

    day_test_cases = [
        (1, 1, "First tick"),
        (1440, 1, "Last tick of day 1"),
        (1441, 2, "First tick of day 2"),
        (2880, 2, "Last tick of day 2"),
        (2881, 3, "First tick of day 3"),
    ]

    for tick, expected_day, description in day_test_cases:
        day = tm.tick_to_day(tick)
        status = "✓" if day == expected_day else "✗"
        if day != expected_day:
            all_passed = False
        print(f"  {status} Tick {tick:6,}: Day {day} (expected {expected_day}) - {description}")

    # Test reverse conversions
    print("\n" + "=" * 80)
    print("REVERSE CONVERSION TESTS")
    print("=" * 80)

    reverse_tests = [
        (1, 1),
        (2, 10081),
        (3, 20161),
        (4, 30241),
    ]

    for week, expected_tick in reverse_tests:
        tick = tm.week_to_tick(week)
        status = "✓" if tick == expected_tick else "✗"
        if tick != expected_tick:
            all_passed = False
        print(f"  {status} Week {week} → Tick {tick:,} (expected {expected_tick:,})")

    # Test week and day to tick conversion
    print("\n" + "=" * 80)
    print("WEEK + DAY TO TICK TESTS")
    print("=" * 80)

    combined_tests = [
        (1, 1, 1, "Week 1, Monday"),
        (1, 7, 8641, "Week 1, Sunday"),
        (2, 1, 10081, "Week 2, Monday"),
        (2, 3, 12961, "Week 2, Wednesday"),
    ]

    for week, day_of_week, expected_tick, description in combined_tests:
        tick = tm.week_and_day_to_tick(week, day_of_week)
        status = "✓" if tick == expected_tick else "✗"
        if tick != expected_tick:
            all_passed = False
        print(f"  {status} {description}: Tick {tick:,} (expected {expected_tick:,})")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("\nThe tick conversion utilities are working correctly!")
        print("Projects will now start at their designated calendar weeks.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("\nPlease review the failures above.")
        return 1

if __name__ == "__main__":
    exit_code = test_tick_conversions()
    sys.exit(exit_code)
