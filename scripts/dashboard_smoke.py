from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.ui_verification import UIVerificationService  # noqa: E402


def main() -> int:
    service = UIVerificationService(get_settings())
    smoke = service.dashboard_smoke("script-dashboard-smoke")
    failed = [check for check in smoke.checks if check.status != "pass"]

    print("Dashboard Smoke")
    print(f"Status: {smoke.status.upper()}")
    print(
        "Summary: "
        f"views={smoke.summary['views_present']}/{smoke.summary['view_count']} "
        f"endpoints={smoke.summary['endpoints_referenced']}/{smoke.summary['endpoint_count']} "
        f"routes={smoke.summary['routes_defined']}/{smoke.summary['endpoint_count']} "
        f"artifact_tabs={smoke.summary['generated_artifact_tab_count']}"
    )
    print("")
    print("Checked views:")
    for view in smoke.expected_views:
        marker = "PASS" if view.status == "pass" else "FAIL"
        endpoints = ", ".join(view.endpoint_paths) or "no endpoints"
        print(f"- {marker} {view.label} [{endpoints}]")
    print("")
    print("Checked endpoints:")
    for endpoint in smoke.endpoint_references:
        marker = "PASS" if endpoint.status == "pass" else "FAIL"
        print(
            f"- {marker} {endpoint.method} {endpoint.path} "
            f"dashboard={endpoint.dashboard_referenced} route={endpoint.route_defined}"
        )

    if failed:
        print("")
        print("Failed checks:")
        for check in failed:
            print(f"- {check.check_id}: {check.evidence}")
        print("Result: FAIL")
        return 1

    print("")
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
