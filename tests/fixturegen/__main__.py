import sys
from . import write_all

for fid, fx in write_all(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out").items():
    print(fid, ", ".join(f"{n} {len(b)}" for n, b in fx.files.items()))
