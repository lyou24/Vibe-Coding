import sys, pathlib, base64
m, f, b = sys.argv[1], sys.argv[2], sys.argv[3]
d = base64.b64decode(b)
with open(f, m) as fp: fp.write(d)
