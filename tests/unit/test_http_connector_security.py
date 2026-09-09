# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import pytest

from recordlane.connectors.http import PaginatedHttpConnector


def resolved(address: str):
    return [(2, 1, 6, "", (address, 443))]


def test_rejects_credentials_and_unapproved_hosts():
    with pytest.raises(ValueError): PaginatedHttpConnector("https://user:secret@example.test", {"example.test"})
    with pytest.raises(ValueError): PaginatedHttpConnector("https://other.test", {"example.test"})


def test_private_and_metadata_destinations_need_specific_authorization():
    with patch("socket.getaddrinfo", return_value=resolved("10.0.0.7")):
        with pytest.raises(ValueError, match="private connector"):
            PaginatedHttpConnector("https://erp.internal", {"erp.internal"})
        PaginatedHttpConnector("https://erp.internal", {"erp.internal"}, allow_private_networks=True)
    with patch("socket.getaddrinfo", return_value=resolved("169.254.169.254")):
        with pytest.raises(ValueError, match="metadata"):
            PaginatedHttpConnector("https://metadata.internal", {"metadata.internal"}, allow_private_networks=True)


def test_disallows_cleartext_remote_destination():
    with patch("socket.getaddrinfo", return_value=resolved("203.0.113.10")):
        with pytest.raises(ValueError, match="unencrypted"):
            PaginatedHttpConnector("http://source.example", {"source.example"})
