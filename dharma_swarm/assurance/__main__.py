"""Allow running assurance as: python3 -m dharma_swarm.assurance [scan|status]"""

import sys

from dharma_swarm.assurance.run_scanners import main as scan_main
from dharma_swarm.assurance.status import main as status_main


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        status_main()
    else:
        scan_main()


if __name__ == "__main__":
    main()
