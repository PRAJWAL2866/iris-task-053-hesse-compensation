
"""Command-line entry point."""

import logging
import sys

from .pipeline import run_pipeline


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        summary = run_pipeline()
    except Exception:
        logging.exception("Compensation-register ingestion failed")
        return 1

    print("Ingestion summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
