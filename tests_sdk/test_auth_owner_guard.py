"""Owner identity uses real REST objects; no HTTP or persisted sessions."""
import asyncio
from types import SimpleNamespace

import pytest

from bitteam_sdk import SessionAuth
from bitteam_sdk.rest import BitTeamRestAPI


@pytest.mark.parametrize("change", ["replacement", "missing"])
def test_real_owner_requires_exact_auth_even_when_lifecycle_matches(change):
    auth = SessionAuth()
    owner = BitTeamRestAPI(auth=auth)
    if change == "replacement":
        other = SessionAuth()
        assert other._lifecycle == auth._lifecycle
        other.bind(owner)
        owner.auth = other
    else:
        del owner.auth
    with pytest.raises(asyncio.CancelledError):
        auth._assert_owner()


def test_legacy_duck_transport_without_auth_remains_usable():
    auth = SessionAuth()
    auth.bind(SimpleNamespace())
    auth._assert_owner()


def test_duck_transport_with_explicit_different_auth_is_rejected():
    auth = SessionAuth()
    auth.bind(SimpleNamespace(auth=SessionAuth()))
    with pytest.raises(asyncio.CancelledError):
        auth._assert_owner()


def test_same_owner_refresh_does_not_change_ownership():
    auth = SessionAuth()
    owner = BitTeamRestAPI(auth=auth)
    auth._generation += 1
    auth._assert_owner()
    assert owner.auth is auth
