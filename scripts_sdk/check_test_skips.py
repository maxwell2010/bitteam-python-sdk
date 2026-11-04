"""Reject hidden test skips; only native Windows DPAPI may skip off Windows."""
import argparse
import sys
from xml.etree import ElementTree


def check_report(path, *, platform=sys.platform):
    root = ElementTree.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases:
        raise ValueError("JUnit report contains no test cases")
    allowed = "test_real_windows_dpapi_roundtrip_and_integrity"
    for case in cases:
        if case.find("skipped") is None:
            continue
        if (platform == "win32" or case.get("name") != allowed or
                not case.get("classname", "").endswith("test_session_cache")):
            raise ValueError("Unexpected skipped test: " + case.get("name", "unknown"))
    print("Skip audit passed for", platform)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    check_report(parser.parse_args().report)
