"""Start Pulse and open the default browser. No third-party dependencies."""
import argparse, threading, webbrowser
from pathlib import Path
from server import make_server

p=argparse.ArgumentParser(description=__doc__); p.add_argument('--port',type=int,default=8765); p.add_argument('--db',default=str(Path(__file__).resolve().parent/'data'/'pulse.sqlite3')); args=p.parse_args()
try: server=make_server(args.db,port=args.port)
except OSError as e: raise SystemExit(f'Unable to start Pulse: {e}. Try another port, e.g. --port 8766.')
url=f'http://127.0.0.1:{server.server_port}/'; print(f'Pulse is ready: {url}\nKeep this terminal open. Ctrl+C stops the server.',flush=True)
threading.Timer(.35,lambda:webbrowser.open(url)).start()
try: server.serve_forever()
except KeyboardInterrupt: pass
finally: server.stopping.set(); server.store.wake(); server.server_close()
