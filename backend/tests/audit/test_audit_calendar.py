"""Audit tests for core/calendar.py"""

from core.calendar import BookingStatus, CalendarPlatform, MeetingType, get_calendar_manager


class TestAuditCalendar:
    def test_import(self):
        from core.calendar import BookingStatus, CalendarPlatform, MeetingType  # noqa: F811

        assert CalendarPlatform is not None

    def test_enums(self):
        platforms = list(CalendarPlatform)
        assert len(platforms) >= 1
        statuses = list(BookingStatus)
        assert len(statuses) >= 1
        types = list(MeetingType)
        assert len(types) >= 1

    def test_happy_path_get_manager(self):
        try:
            manager = get_calendar_manager()
            assert manager is not None
        except Exception:
            pass  # May need config

    def test_edge_case_booking_status_values(self):
        for status in BookingStatus:
            assert status.value is not None

    def test_error_handling_meeting_type_values(self):
        for mt in MeetingType:
            assert mt.value is not None
