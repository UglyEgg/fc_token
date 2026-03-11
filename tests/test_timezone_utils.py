"""Tests for timezone resolution helpers."""

from __future__ import annotations

import os
import unittest
from datetime import timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fc_token import timezone_utils as tz_utils


class TimezoneUtilsTests(unittest.TestCase):
    def test_saved_setting_overrides_env_and_system(self) -> None:
        with patch.object(tz_utils, "_read_saved_zone_name", return_value="America/Chicago"):
            with patch.object(tz_utils, "_read_env_zone_name", return_value="Europe/Berlin"):
                with patch.object(tz_utils, "_read_system_zone_name", return_value="Asia/Tokyo"):
                    resolved = tz_utils.resolve_local_timezone("UTC")

        self.assertEqual(resolved.display_name, "America/Chicago")
        self.assertEqual(resolved.canonical_name, "America/Chicago")
        self.assertEqual(getattr(resolved.tzinfo, "key", None), "America/Chicago")
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.SETTINGS)

    def test_invalid_setting_falls_back_to_valid_environment_zone(self) -> None:
        with patch.object(tz_utils, "_read_saved_zone_name", return_value="Mars/Phobos"):
            with patch.object(tz_utils, "_read_env_zone_name", return_value="Europe/Berlin"):
                with patch.object(tz_utils, "_read_system_zone_name", return_value="Asia/Tokyo"):
                    resolved = tz_utils.resolve_local_timezone("UTC")

        self.assertEqual(resolved.display_name, "Europe/Berlin")
        self.assertEqual(getattr(resolved.tzinfo, "key", None), "Europe/Berlin")
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.ENVIRONMENT)

    def test_system_timezone_name_is_used_when_no_setting_or_env_exists(self) -> None:
        with patch.object(tz_utils, "_read_saved_zone_name", return_value=None):
            with patch.object(tz_utils, "_read_env_zone_name", return_value=None):
                with patch.object(tz_utils, "_read_system_zone_name", return_value="America/Chicago"):
                    resolved = tz_utils.resolve_local_timezone("UTC")
                    zone_key = tz_utils.get_local_zone_key("UTC")

        self.assertEqual(resolved.display_name, "America/Chicago")
        self.assertEqual(zone_key, "America/Chicago")
        self.assertEqual(getattr(resolved.tzinfo, "key", None), "America/Chicago")
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.SYSTEM)

    def test_system_fixed_offset_fallback_is_used_before_default(self) -> None:
        fixed_zone = timezone(timedelta(hours=-6), name="UTC-06")
        with patch.object(tz_utils, "_read_saved_zone_name", return_value=None):
            with patch.object(tz_utils, "_read_env_zone_name", return_value=None):
                with patch.object(tz_utils, "_read_system_zone_name", return_value=None):
                    with patch.object(tz_utils, "_read_system_zone_fallback", return_value=fixed_zone):
                        resolved = tz_utils.resolve_local_timezone("UTC")
                        zone_key = tz_utils.get_local_zone_key("UTC")

        self.assertIs(resolved.tzinfo, fixed_zone)
        self.assertEqual(resolved.display_name, "UTC-06")
        self.assertIsNone(resolved.canonical_name)
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.SYSTEM_FALLBACK)
        self.assertIsNone(zone_key)

    def test_default_timezone_used_when_no_other_source_resolves(self) -> None:
        with patch.object(tz_utils, "_read_saved_zone_name", return_value=None):
            with patch.object(tz_utils, "_read_env_zone_name", return_value=None):
                with patch.object(tz_utils, "_read_system_zone_name", return_value=None):
                    with patch.object(tz_utils, "_read_system_zone_fallback", return_value=None):
                        resolved = tz_utils.resolve_local_timezone("UTC")

        self.assertEqual(resolved.display_name, "UTC")
        self.assertEqual(resolved.canonical_name, "UTC")
        self.assertEqual(resolved.tzinfo, ZoneInfo("UTC"))
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.DEFAULT)

    def test_invalid_default_falls_back_to_utc(self) -> None:
        with patch.object(tz_utils, "_read_saved_zone_name", return_value=None):
            with patch.object(tz_utils, "_read_env_zone_name", return_value=None):
                with patch.object(tz_utils, "_read_system_zone_name", return_value=None):
                    with patch.object(tz_utils, "_read_system_zone_fallback", return_value=None):
                        resolved = tz_utils.resolve_local_timezone("Not/AZone")

        self.assertEqual(resolved.display_name, "UTC")
        self.assertEqual(resolved.canonical_name, "UTC")
        self.assertEqual(resolved.source, tz_utils.TimezoneSource.FALLBACK)

    def test_env_reads_tz_before_timezone(self) -> None:
        with patch.dict(os.environ, {"TZ": "America/Chicago", "TIMEZONE": "Asia/Tokyo"}, clear=True):
            self.assertEqual(tz_utils._read_env_zone_name(), "America/Chicago")

    def test_env_timezone_value_is_trimmed(self) -> None:
        with patch.dict(os.environ, {"TZ": "  America/Chicago  "}, clear=True):
            self.assertEqual(tz_utils._read_env_zone_name(), "America/Chicago")

    def test_system_zone_name_from_localtime_uses_zoneinfo_path(self) -> None:
        from unittest.mock import Mock

        localtime_path = Mock()
        zoneinfo_root = tz_utils._ZONEINFO_ROOT
        localtime_path.resolve.return_value = zoneinfo_root / "America/Chicago"

        with patch.object(tz_utils, "_LOCALTIME_PATH", localtime_path):
            self.assertEqual(
                tz_utils._read_system_zone_name_from_localtime(),
                "America/Chicago",
            )

    def test_display_name_for_fixed_offset_zone_uses_tzname(self) -> None:
        fixed_zone = timezone(timedelta(hours=-5), name="UTC-05")
        self.assertEqual(tz_utils._display_name_for_zone(fixed_zone, None), "UTC-05")

    def test_get_local_zone_key_prefers_resolved_canonical_name(self) -> None:
        resolved = tz_utils.ResolvedTimezone(
            tzinfo=ZoneInfo("America/Chicago"),
            display_name="America/Chicago",
            canonical_name="America/Chicago",
            source=tz_utils.TimezoneSource.SYSTEM,
        )
        with patch.object(tz_utils, "resolve_local_timezone", return_value=resolved):
            self.assertEqual(tz_utils.get_local_zone_key("UTC"), "America/Chicago")

    def test_get_local_zone_key_returns_none_for_noncanonical_system_fallback(self) -> None:
        resolved = tz_utils.ResolvedTimezone(
            tzinfo=timezone(timedelta(hours=-6), name="UTC-06"),
            display_name="UTC-06",
            canonical_name=None,
            source=tz_utils.TimezoneSource.SYSTEM_FALLBACK,
        )
        with patch.object(tz_utils, "resolve_local_timezone", return_value=resolved):
            self.assertIsNone(tz_utils.get_local_zone_key("UTC"))

    def test_timezone_dialog_state_requires_explicit_selection_for_noncanonical_zone(self) -> None:
        resolved = tz_utils.ResolvedTimezone(
            tzinfo=timezone(timedelta(hours=-6), name="UTC-06"),
            display_name="UTC-06",
            canonical_name=None,
            source=tz_utils.TimezoneSource.SYSTEM_FALLBACK,
        )
        with patch.object(tz_utils, "resolve_local_timezone", return_value=resolved):
            state = tz_utils.get_timezone_dialog_state("UTC")

        self.assertEqual(state.current_display_name, "UTC-06")
        self.assertIsNone(state.preselected_key)
        self.assertEqual(state.placeholder_label, "System local (UTC-06)")

    def test_timezone_dialog_state_preselects_canonical_zone(self) -> None:
        resolved = tz_utils.ResolvedTimezone(
            tzinfo=ZoneInfo("America/Chicago"),
            display_name="America/Chicago",
            canonical_name="America/Chicago",
            source=tz_utils.TimezoneSource.SYSTEM,
        )
        with patch.object(tz_utils, "resolve_local_timezone", return_value=resolved):
            state = tz_utils.get_timezone_dialog_state("UTC")

        self.assertEqual(state.current_display_name, "America/Chicago")
        self.assertEqual(state.preselected_key, "America/Chicago")
        self.assertIsNone(state.placeholder_label)


if __name__ == "__main__":
    unittest.main()
