"""Interactive real-account check. Credentials stay in the local terminal."""
import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
import sys
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from . import BitTeamClient, SessionAuth, AuthState, LoginResult, BitTeamAPIError, SessionCache


# This allowlist is deliberately independent of the full endpoint catalog.
ALLOWED = {
    ("auth2.bit.team", "POST", "/v1/clients/web/login"): "password_login",
    ("auth2.bit.team", "POST", "/v1/clients/web/login-2fa"): "google_2fa",
    ("auth2.bit.team", "POST", "/v1/authorize/send-code"): "send_device_code",
    ("auth2.bit.team", "POST", "/v1/authorize/check-code"): "confirm_device",
    ("bit.team", "POST", "/trade/api/login-auth"): "spot_exchange",
    ("bit.team", "GET", "/trade/api/address/wallets"): "read_balance",
    ("bit.team", "POST", "/trade/api/refresh-token"): "refresh",
    ("bit.team", "POST", "/trade/api/logout"): "logout",
}


def balance_shape(payload):
    if not isinstance(payload, dict) or payload.get("ok") is False or not isinstance(payload.get("result"), dict):
        raise ValueError("Balance response has an unexpected structure")
    # Neither values nor currency names are included in this summary.
    return {"response_type": type(payload["result"]).__name__}


class AccountCheck:
    def __init__(self, client, report_path):
        self.client = client
        self.path = Path(report_path)
        self.report = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "prepared", "steps": [], "requests": [],
            "two_factor": "not_requested", "device_code": "not_requested"}
        self.original_send = client.rest._send
        client.rest._send = self.guarded_send

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix="account-check-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.report, stream, ensure_ascii=False, indent=2)
            os.replace(filename, self.path)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def step(self, name, status, **safe_fields):
        self.report["steps"].append({"step": name, "status": status, **safe_fields})
        self.report["status"] = "running"
        self.save()
        print(f"[{status}] {name}", flush=True)

    def cookies(self):
        session = self.client.rest._session
        if session is None:
            return []
        return [{"name": cookie.key, "domain": cookie["domain"], "path": cookie["path"],
                 "secure": bool(cookie["secure"]), "httponly": bool(cookie["httponly"]),
                 "samesite": cookie["samesite"], "max_age": cookie["max-age"],
                 "expires": cookie["expires"]} for cookie in session.cookie_jar]

    async def guarded_send(self, method, url, **kwargs):
        target = urlsplit(str(url))
        key = (target.hostname, method.upper(), target.path)
        if (target.scheme != "https" or target.port not in (None, 443)
                or target.username is not None or target.query or key not in ALLOWED):
            raise RuntimeError("Account check blocked a request outside its authentication/balance allowlist")
        entry = {"operation": ALLOWED[key], "status": "pending"}
        self.report["requests"].append(entry)
        self.save()
        try:
            result = await self.original_send(method, url, **kwargs)
            entry["status"] = "ok"
            entry["response_type"] = type(result).__name__
            # Only documented boolean auth flags are captured, never data values.
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, dict):
                entry["auth_flags"] = {key: data[key] for key in
                    ("email_confirm", "double_auth_google", "is_authorize") if isinstance(data.get(key), bool)}
            return result
        except BitTeamAPIError as error:
            entry.update(status="failed", http_status=error.status,
                         code=error.code if isinstance(error.code, int) else None)
            raise
        except Exception as error:
            entry.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            entry["cookie_attributes"] = self.cookies()
            self.save()


async def terminal_prompt(label, *, secret=True):
    if not os.isatty(0):
        raise RuntimeError("Open this check in an interactive terminal")
    return await asyncio.to_thread(getpass.getpass if secret else input, label)


async def window_prompt(label, *, secret=True):
    """Local native form. Its fields are never sent to the agent or report."""
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("BitTeam SDK - проверка аккаунта")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    labels = {
        "BitTeam email (hidden): ": "Почта аккаунта BitTeam",
        "BitTeam password (hidden): ": "Пароль аккаунта BitTeam",
        "Google 2FA code - 6 digits (hidden): ": "Код Google Authenticator - 6 цифр",
        "Device code from email or Telegram - 4 digits (hidden): ": "Код из почты или Telegram - 4 цифры",
        "Where did the code arrive? [email/telegram/unknown]: ": "Где получен код? Введите email или telegram",
    }
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=labels.get(label, label), font=("Segoe UI", 11)).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
    mask = secret and not label.startswith("BitTeam email")
    entry = ttk.Entry(frame, width=48, show="*" if mask else "", font=("Segoe UI", 11))
    entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
    counter = ttk.Label(frame, text="Поле пустое", foreground="#9b1c1c")
    counter.grid(row=2, column=0, columnspan=4, pady=(8, 0), sticky="w")
    notice = ttk.Label(frame, text="Данные используются локально и не записываются в отчёт.")
    notice.grid(row=3, column=0, columnspan=4, pady=(8, 8), sticky="w")
    result = []

    def update_count(event=None):
        count = len(entry.get())
        counter.configure(text=f"Введено символов: {count}" if count else "Поле пустое",
                          foreground="#166534" if count else "#9b1c1c")
        continue_button.configure(state="normal" if count else "disabled")

    def paste():
        entry.focus_set()
        try:
            value = root.clipboard_get()
        except tk.TclError:
            notice.configure(text="В буфере нет текста. Скопируйте нужное значение заново.")
            update_count()
            return
        if not mask:
            value = value.strip()
        if entry.selection_present():
            entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        entry.insert(tk.INSERT, value)
        value = None
        notice.configure(text="Текст вставлен. Проверьте число символов.")
        update_count()

    def clear():
        entry.delete(0, tk.END)
        update_count()
        entry.focus_set()

    def keyboard_paste(event=None):
        paste()
        return "break"

    def control_key(event):
        # Windows VK_V remains 86 even when the active keyboard layout is RU.
        if event.keycode == 86 or event.keysym.lower() == "v":
            return keyboard_paste(event)

    revealed = tk.BooleanVar(master=root, value=False)

    def toggle_visibility():
        entry.configure(show="" if revealed.get() else "*")
        notice.configure(text="Значение отображается." if revealed.get() else "Значение скрыто.")
        entry.focus_set()

    def submit(event=None):
        value = entry.get()
        if not value:
            notice.configure(text="Введите значение или нажмите «Вставить».")
            return
        result.append(value)
        entry.delete(0, tk.END)
        root.destroy()

    ttk.Button(frame, text="Вставить", command=paste).grid(row=1, column=1)
    ttk.Button(frame, text="Очистить", command=clear).grid(row=1, column=2, padx=(8, 0))
    if mask:
        ttk.Checkbutton(frame, text="👁", variable=revealed, command=toggle_visibility,
                        style="Toolbutton").grid(row=1, column=3, padx=(8, 0))
    continue_button = ttk.Button(frame, text="Продолжить", command=submit, state="disabled")
    continue_button.grid(row=4, column=0, sticky="e", pady=(8, 0))
    ttk.Button(frame, text="Отмена", command=root.destroy).grid(row=4, column=1, pady=(8, 0))
    entry.bind("<KeyRelease>", update_count)
    entry.bind("<Control-KeyPress>", control_key)
    entry.bind("<Shift-Insert>", keyboard_paste)
    entry.bind("<<Paste>>", lambda event: root.after_idle(update_count))
    root.bind("<Return>", submit)
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 2
    root.geometry(f"+{x}+{y}")
    root.after(80, lambda: (root.lift(), root.focus_force(), entry.focus_set()))
    root.mainloop()
    if not result:
        raise asyncio.CancelledError()
    return result[0]


async def run_check(report_path, *, prompt=terminal_prompt, client=None, cache_profile=None, keep_session=False):
    cache = SessionCache(cache_profile) if cache_profile else None
    client = client or BitTeamClient(auth=SessionAuth(cache=cache), timeout=30, max_read_retries=0)
    if keep_session and client.auth.cache is None:
        raise ValueError("Keeping a session requires an encrypted session cache")
    check = AccountCheck(client, report_path)
    success = False
    try:
        check.save()
        restored = False
        if client.auth.cache is not None:
            check.step("session_restore", "started")
            restored = await client.resume_session()
            check.step("session_restore", "ok" if restored else "fresh_login_required")
        check.report["session_restored"] = restored
        if restored:
            result = LoginResult(AuthState.READY)
        else:
            check.step("credentials", "waiting_for_local_input")
            email = await prompt("BitTeam email (hidden): ")
            password = await prompt("BitTeam password (hidden): ")
            check.step("password_login", "started")
            try:
                result = await client.login(email.strip(), password)
            finally:
                password = None
                email = None
            check.step("password_login", "ok", next_state=result.state.value)
        if result.state == AuthState.EMAIL_CONFIRMATION_REQUIRED:
            check.step("registration_email", "required_on_website")
            return False
        if result.state == AuthState.TWO_FACTOR_REQUIRED:
            check.report["two_factor"] = "requested"
            check.step("google_2fa", "waiting_for_local_input")
            code = await prompt("Google 2FA code - 6 digits (hidden): ")
            try:
                result = await client.submit_totp(code.strip())
            finally:
                code = None
            check.report["two_factor"] = "passed"
            check.step("google_2fa", "ok", next_state=result.state.value)
        if result.state == AuthState.DEVICE_CONFIRMATION_REQUIRED:
            check.report["device_code"] = "requested"
            check.step("send_device_code", "started")
            await client.send_device_code()
            check.step("device_code", "waiting_for_local_input")
            code = await prompt("Device code from email or Telegram - 4 digits (hidden): ")
            try:
                result = await client.confirm_device(code.strip(), remember=False)
            finally:
                code = None
            check.report["device_code"] = "passed"
            source = await prompt("Where did the code arrive? [email/telegram/unknown]: ", secret=False)
            check.report["device_delivery_user_reported"] = source.strip().lower() if source.strip().lower() in ("email", "telegram") else "unknown"
            check.step("device_code", "ok", next_state=result.state.value)
        if result.state != AuthState.READY:
            check.step("authentication", "incomplete", state=result.state.value)
            return False
        check.step("spot_session", "ok")
        check.step("balance_before_refresh", "started")
        shape = balance_shape(await client.get_balance())
        check.step("balance_before_refresh", "ok", **shape)
        previous_access, previous_refresh = client.auth._access, client.auth._refresh
        generation = client.auth.generation
        check.step("refresh", "started")
        await client.refresh()
        check.step("refresh", "ok", generation_advanced=client.auth.generation > generation,
                   access_changed=client.auth._access != previous_access,
                   refresh_changed=client.auth._refresh != previous_refresh)
        previous_access = previous_refresh = None
        check.step("balance_after_refresh", "started")
        shape = balance_shape(await client.get_balance())
        check.step("balance_after_refresh", "ok", **shape)
        success = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        try:
            check.step("check", "cancelled")
        except Exception:
            pass
        raise
    except Exception as error:
        safe = {"error_type": type(error).__name__}
        if isinstance(error, BitTeamAPIError):
            safe.update(http_status=error.status, code=error.code if isinstance(error.code, int) else None)
        try:
            check.step("check", "failed", **safe)
        except Exception:
            raise error
        print("Check stopped. Only sanitized diagnostics were saved; no automatic login retry.", flush=True)
        return False
    finally:
        primary_error = sys.exc_info()[0] is not None
        try:
            try:
                if keep_session:
                    client.auth.save_session()
                    check.step("encrypted_session_cache", "ok" if success else "preserved_after_incomplete_check",
                               cache_saved=client.auth.cache.exists)
                else:
                    await client.logout()
                    check.step("session_cleanup", "ok", local_cookies_cleared=not check.cookies())
            except Exception as error:
                success = False
                try:
                    check.step("session_cleanup", "failed", error_type=type(error).__name__)
                except Exception:
                    raise error
        except BaseException:
            if not primary_error:
                raise
        finally:
            # Closing the transport must not depend on diagnostics or cache writes.
            pending_error = primary_error or sys.exc_info()[0] is not None
            try:
                await client.close()
            except BaseException as error:
                success = False
                if not pending_error:
                    if not isinstance(error, Exception):
                        raise
                    check.step("transport_close", "failed", error_type=type(error).__name__)
            finally:
                pending_error = pending_error or sys.exc_info()[0] is not None
                check.report["status"] = "passed" if success and not pending_error else "incomplete"
                check.report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                try:
                    check.save()
                except Exception:
                    if not pending_error:
                        raise
                print("Report:", check.path, flush=True)
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--window-input", action="store_true")
    parser.add_argument("--cache-profile")
    parser.add_argument("--keep-session", action="store_true")
    arguments = parser.parse_args()
    if arguments.keep_session and not arguments.cache_profile:
        parser.error("--keep-session requires --cache-profile")
    passed = asyncio.run(run_check(arguments.report, prompt=window_prompt if arguments.window_input else terminal_prompt,
                                  cache_profile=arguments.cache_profile, keep_session=arguments.keep_session))
    raise SystemExit(0 if passed else 1)
