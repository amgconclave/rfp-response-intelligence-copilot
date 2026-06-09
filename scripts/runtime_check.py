from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.runtime_demo import RuntimeDemoService  # noqa: E402


def main() -> int:
    readiness = RuntimeDemoService(get_settings()).readiness("script-runtime-check")
    missing_dependencies = [
        check["package"]
        for check in readiness.dependency_checks
        if check["required"] and not check["installed"]
    ]

    print("Runtime Demo Readiness")
    print(f"Status: {readiness.status.upper()}")
    print(f"Provider: {readiness.provider_mode}")
    print(f"Vector store: {readiness.vector_store_mode}")
    print(f"Runtime pack dir: {readiness.storage_runtime_pack_dir}")
    print("")
    print("Dependency checks:")
    for check in readiness.dependency_checks:
        marker = "PASS" if check["installed"] else ("WARN" if not check["required"] else "FAIL")
        print(f"- {marker} {check['package']}: {check['purpose']}")
    print("")
    print("Read-only port checks:")
    for check in readiness.process_port_checks:
        marker = "LISTENING" if check["listening"] else "FREE"
        print(f"- {marker} {check['service']} {check['host']}:{check['port']} ({check['check_type']})")
    print("")
    print("Start commands:")
    for command in readiness.local_run_commands[:4]:
        print(f"- {command}")
    print("")
    print("Health URLs:")
    for item in readiness.expected_health_urls:
        print(f"- {item['label']}: {item['url']}")

    if missing_dependencies:
        print("")
        print("Missing required dependencies:")
        for name in missing_dependencies:
            print(f"- {name}")
        print('Run: python -m pip install -e ".[dev]"')
        return 1

    print("")
    print("Result: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
