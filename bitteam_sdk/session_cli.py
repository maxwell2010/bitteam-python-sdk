"""Manage an encrypted session: status, logout, or clear local data."""
import argparse
import asyncio
from . import BitTeamClient, SessionAuth, SessionCache, SessionCacheError, BitTeamAPIError


async def manage(action, profile):
    cache = SessionCache(profile)
    if action == "status":
        print("Encrypted session cache exists." if cache.exists else "No cached session.")
        return True
    if action == "clear":
        cache.delete()
        print("Local session cache deleted. No server request was made.")
        return True
    async with BitTeamClient(auth=SessionAuth(cache=cache)) as client:
        if await client.resume_session(validate=False):
            try:
                await client.logout()
            except BitTeamAPIError:
                print("Local data cleared; server logout could not be confirmed.")
                return False
        else:
            await client.clear_session()
        print("Logged out; local authentication data cleared.")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "logout", "clear"))
    parser.add_argument("--profile", default="main")
    args = parser.parse_args()
    try:
        ok = asyncio.run(manage(args.action, args.profile))
    except Exception:
        # Custom cache/protector and cleanup failures may contain private data.
        print("Session operation failed. No credentials were displayed.")
        ok = False
    raise SystemExit(0 if ok else 1)
