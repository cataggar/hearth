"""Bounded negative controls against the exact retained pre-fix Git blob."""

import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))

import custody
import hosted
import test_hosted


def main():
    blob = "41561cad864b4dce2ed8d019a1768ee49fabe34f"
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        f"https://api.github.com/repos/cataggar/hearth/git/blobs/{blob}", headers=headers)
    with opener.open(request, timeout=30) as response:
        record = json.loads(response.read(65536))
    assert record["sha"] == blob and record["encoding"] == "base64"
    source = base64.b64decode(record["content"].replace("\n", ""), validate=True)
    assert hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest() == blob
    directory = hosted.bench.ROOT / ".ci/custody-before-review"
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    original = custody.Supervisor
    try:
        (directory / "custody.py").write_bytes(source)
        node = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.ClassDef) and node.name == "Supervisor")
        namespace = custody.__dict__.copy()
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<immutable-9ee9-custody>", "exec"), namespace)
        custody.Supervisor = namespace["Supervisor"]
        names = [
            "test_exit_reaped_between_liveness_and_lookup_is_normal_no_signal",
            "test_registration_error_preserves_failed_receipt_and_cleans_other_children",
        ]
        with patch.object(hosted, "__file__", str(directory / "hosted.py")):
            suite = unittest.TestSuite(test_hosted.DescendantCustody(name) for name in names)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.testsRun == 2 and not result.skipped
        assert len(result.errors) == len(result.failures) == 1
        assert "refusing changed owned PID generation" in result.errors[0][1]
        assert "injected per-registration verification refusal" in result.failures[0][1]
        print(json.dumps({"immutable_9ee9_negative_controls": 2, "expected_errors": 1,
                          "expected_failures": 1, "skipped": 0, "verified_git_blob": blob,
                          "owned_fixture_children_reconciled": True}))
    finally:
        custody.Supervisor = original
        shutil.rmtree(directory)


if __name__ == "__main__":
    os.umask(0o077)
    main()
