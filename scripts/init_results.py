"""Print a complete NOT RUN matrix; never perform identity tests or cloud writes."""

import json

from identity_lab.catalog import CONFIGURATIONS, PATTERNS


def matrix() -> dict:
    return {
        "schema": 1,
        "results": [
            {
                "alias": alias, "pattern": pattern, "configuration": configuration,
                "status": "NOT RUN", "reason": "not-run", "observation": "unavailable",
                "expectation": "preserve-user" if configuration == "user" else "different-principal-or-denial",
            }
            for alias in ("user-a", "user-b")
            for pattern, (_, _, route) in PATTERNS.items()
            for configuration in CONFIGURATIONS
            if route != "probe" or configuration == "user"
        ],
    }


if __name__ == "__main__":
    print(json.dumps(matrix(), indent=2))
