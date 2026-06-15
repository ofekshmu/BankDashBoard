import sys, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
try:
    exec(open("WebApp.py", encoding="utf-8").read())
except Exception as e:
    print("FATAL:", e, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
