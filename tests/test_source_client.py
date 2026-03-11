from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fc_token.core.source import (
    ActivationSourceClient,
    SourceNetworkError,
    SourceParseError,
)
from fc_token.models import UTC


class SourceClientTests(unittest.TestCase):
    def test_fetch_codes_returns_structured_result(self) -> None:
        response = Mock()
        response.text = "2024-01-01 00:00:00 - 2024-01-01 01:00:00\nTOKEN123\n"
        response.content = response.text.encode("utf-8")
        response.raise_for_status.return_value = None

        session = Mock()
        session.get.return_value = response

        client = ActivationSourceClient(
            session=session,
            identities=[("Test", "UA")],
        )
        with patch("fc_token.core.source.datetime") as dt_mod:
            dt_mod.now.return_value = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
            result = client.fetch_codes("http://example.com")

        self.assertEqual(result.identity_label, "Test")
        self.assertEqual(result.raw_bytes, len(response.content))
        self.assertEqual(len(result.codes), 1)

    def test_fetch_codes_raises_parse_error_for_empty_result(self) -> None:
        response = Mock()
        response.text = "no codes here"
        response.content = response.text.encode("utf-8")
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        client = ActivationSourceClient(session=session, identities=[("Test", "UA")])

        with self.assertRaises(SourceParseError):
            client.fetch_codes("http://example.com")

    def test_fetch_codes_wraps_network_errors(self) -> None:
        session = Mock()
        import requests
        session.get.side_effect = requests.RequestException('boom')
        client = ActivationSourceClient(session=session, identities=[("Test", "UA")])

        with self.assertRaises(Exception):
            client.fetch_codes("http://example.com")
