# =========================================================
# gmail_token_generator.py
#
# Legacy entry point — same OAuth flow as before, plus Conlecta .env sync.
# Equivalent to: python3 TokenGenerator.py --generate [--manual] [--replace]
# =========================================================

import sys

from TokenGenerator import main


if __name__ == "__main__":
    argv = ["TokenGenerator.py", "--generate", "--replace"]
    for arg in sys.argv[1:]:
        if arg in ("--generate",):
            continue
        argv.append(arg)
    raise SystemExit(main(argv))
