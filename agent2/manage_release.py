"""Release bootstrap; packaging/install operations require only Python's stdlib."""
from sme_fraud.release_manager import main

if __name__ == '__main__':
    raise SystemExit(main())
