"""Interactive login example with device-code delivery and session logout.

Run explicitly with python -m bitteam_sdk.auth_example. This is not a read-only
probe: login and device confirmation may send codes; logout revokes the session.
"""
import argparse
import asyncio
import getpass

from . import BitTeamClient, SessionAuth, ApiKeyAuth, AuthState, BitTeamAPIError


async def prompt(label, *, secret=False):
    return await asyncio.to_thread(getpass.getpass if secret else input, label)


async def main(api_keys=False):
    if api_keys:
        auth = ApiKeyAuth(await prompt("API key: ", secret=True), await prompt("API secret: ", secret=True))
    else:
        auth = SessionAuth()
    async with BitTeamClient(auth=auth) as client:
        try:
            if api_keys:
                result = await client.init()
            else:
                email = await prompt("Email: ")
                result = await client.login(email, await prompt("Password: ", secret=True))
                if result.state == AuthState.TWO_FACTOR_REQUIRED:
                    result = await client.submit_totp(await prompt("Google 2FA code: ", secret=True))
                if result.state == AuthState.DEVICE_CONFIRMATION_REQUIRED:
                    await client.send_device_code()
                    result = await client.confirm_device(
                        await prompt("Device code from email or Telegram: ", secret=True))
            if result.state != AuthState.READY:
                print("Required step:", result.state.value)
                return
            await client.get_balance()
            print("Authentication and balance read succeeded. Balance is not printed.")
        except BitTeamAPIError as exc:
            print(str(exc))
        finally:
            if isinstance(auth, SessionAuth):
                await client.logout()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-keys", action="store_true")
    asyncio.run(main(parser.parse_args().api_keys))
