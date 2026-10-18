"""Windows frozen entry point, including multiprocessing's required guard."""

import multiprocessing

from look_to_ask.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
