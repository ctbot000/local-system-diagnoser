import argparse
import json
import webbrowser

from . import memory, server


def main():
    parser = argparse.ArgumentParser(prog="diagnoser", description="Local system diagnoser")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the UI")
    parser.add_argument("--json", action="store_true", help="print one memory snapshot and exit")
    args = parser.parse_args()

    if args.json:
        print(json.dumps(memory.snapshot(), indent=2))
        return

    httpd = server.serve(args.port)
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"Local system diagnoser at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
