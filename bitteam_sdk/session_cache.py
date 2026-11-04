"""Encrypted session persistence. Never stores account passwords or OTP codes."""
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import tempfile


class SessionCacheError(RuntimeError):
    pass


class WindowsDPAPI:
    """Current-user DPAPI, not machine-wide protection."""

    def __init__(self):
        if sys.platform != "win32":
            raise SessionCacheError("Provide an OS-backed encryption protector on this platform")

    def _transform(self, content, *, decrypt=False):
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        buffer = ctypes.create_string_buffer(content)
        source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        destination = Blob()
        library = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        function = library.CryptUnprotectData if decrypt else library.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        # CRYPTPROTECT_UI_FORBIDDEN=1; no LOCAL_MACHINE flag.
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
            raise SessionCacheError("Windows could not decrypt the session cache" if decrypt else "Windows could not encrypt the session cache")
        try:
            return ctypes.string_at(destination.data, destination.size)
        finally:
            kernel.LocalFree(destination.data)

    def protect(self, content):
        return self._transform(content)

    def unprotect(self, content):
        return self._transform(content, decrypt=True)


class SessionCache:
    MAGIC = b"BITTEAM-SESSION-V1\x00"
    FIELDS = {"version", "base_url", "auth_url", "email", "access", "refresh", "cookies"}

    def __init__(self, profile="default", *, directory=None, protector=None):
        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", profile):
            raise ValueError("Session profile must use letters, digits, underscores or hyphens")
        self.protector = protector if protector is not None else WindowsDPAPI()
        root = Path(directory) if directory is not None else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "BitTeamSDK" / "sessions"
        self.path = root / (profile + ".bin")

    def save(self, payload):
        if set(payload) != self.FIELDS or payload.get("version") != 1:
            raise SessionCacheError("Unexpected session cache schema")
        # Enforce a closed schema so callers cannot accidentally add passwords.
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encrypted = self.MAGIC + self.protector.protect(content)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="session-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self):
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            return None
        if not content.startswith(self.MAGIC) or len(content) > 1024 * 1024:
            raise SessionCacheError("Invalid session cache format")
        try:
            data = json.loads(self.protector.unprotect(content[len(self.MAGIC):]))
        except SessionCacheError:
            raise
        except Exception:
            raise SessionCacheError("Session cache cannot be decrypted or decoded") from None
        if not isinstance(data, dict) or set(data) != self.FIELDS or data.get("version") != 1:
            raise SessionCacheError("Unexpected session cache schema")
        return data

    def delete(self):
        self.path.unlink(missing_ok=True)

    @property
    def exists(self):
        return self.path.is_file()
