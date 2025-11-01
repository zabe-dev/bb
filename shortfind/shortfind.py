#!/usr/bin/env python3

import argparse
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "1.0"
START_TIME = None
INTERRUPTED = False

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    ORANGE = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

class Spinner:
    def __init__(self, message="Processing"):
        self.spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()

        idx = 0
        while self.running:
            sys.stdout.write(f'\r\033[K{Colors.CYAN}{self.spinner[idx]}{Colors.RESET} {self.message}')
            sys.stdout.flush()
            idx = (idx + 1) % len(self.spinner)
            time.sleep(0.1)

        sys.stdout.write('\r\033[K')
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

def signal_handler(signum, frame):
    global INTERRUPTED
    INTERRUPTED = True
    sys.stdout.write('\033[?25h')
    sys.stdout.flush()
    elapsed = (time.time() - START_TIME) if START_TIME else 0
    print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Search interrupted {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def print_banner():
    print(rf"""{Colors.CYAN}
     _               _    __ _           _
 ___| |__   ___  _ _| |_ / _(_)_ __   __| |
/ __| '_ \ / _ \| '__| __| |_| | '_ \ / _` |
\__ \ | | | (_) | |  | |_|  _| | | | | (_| |
|___/_| |_|\___/|_|   \__|_| |_|_| |_|\__,_|
{Colors.RESET}
{Colors.DIM}    IIS Shortname Full Path Finder v{VERSION}{Colors.RESET}
""")

def search_github_api(query, token=None, max_results=1000, extension=None):
    matched_words = set()
    page = 1
    per_page = 100
    total_fetched = 0

    headers = {'User-Agent': 'Mozilla/5.0'}
    if token:
        headers['Authorization'] = f'token {token}'

    search_msg = f"Searching GitHub for '{query}'"
    if extension:
        search_msg += f" with extension '{extension}'"
    spinner = Spinner(search_msg + "...")
    spinner.start()

    while total_fetched < max_results:
        try:
            search_query = f"filename:{query}"
            if extension:
                search_query += f"+extension:{extension}"

            url = f"https://api.github.com/search/code?q={search_query}&per_page={per_page}&page={page}"
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if 'items' not in data or len(data['items']) == 0:
                    break

                for item in data['items']:
                    if 'name' in item:
                        filename = item['name']

                        if extension:
                            file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
                            if file_ext.startswith(extension.lower()):
                                if query.lower() in filename.lower():
                                    matched_words.add(filename)
                        else:
                            if query.lower() in filename.lower():
                                matched_words.add(filename)

                total_fetched += len(data['items'])

                if len(data['items']) < per_page:
                    break

                page += 1
                time.sleep(2)

        except urllib.error.HTTPError as e:
            spinner.stop()
            if e.code == 403:
                print(f"[{Colors.RED}ERR{Colors.RESET}] Rate limit exceeded. Use -t flag with GitHub token")
            elif e.code == 422:
                print(f"[{Colors.ORANGE}WRN{Colors.RESET}] Search query validation failed")
            else:
                print(f"[{Colors.RED}ERR{Colors.RESET}] HTTP error {e.code}")
            return list(matched_words)
        except Exception as e:
            spinner.stop()
            print(f"[{Colors.RED}ERR{Colors.RESET}] {e}")
            return list(matched_words)

    spinner.stop()
    count = len(matched_words)
    if count > 0:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Found {count} unique matches")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] No matches found")

    return list(matched_words)

def save_results(results, output_file):
    try:
        with open(output_file, 'w') as f:
            for word in sorted(results):
                f.write(f"{word}\n")
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Results saved to {output_file}")
    except Exception as e:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to save results: {e}")

def main():
    global START_TIME

    parser = argparse.ArgumentParser(
        description="Find full filenames from IIS shortnames using GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-s", required=True, metavar="QUERY", help="Search query (shortname fragment)")
    parser.add_argument("-o", metavar="output.txt", help="Output file")
    parser.add_argument("-t", metavar="TOKEN", help="GitHub personal access token")
    parser.add_argument("-m", metavar="MAX", type=int, default=1000, help="Maximum results to fetch (default: 1000)")
    parser.add_argument("-e", metavar="EXT", help="Filter by extension (first 3 letters, e.g., 'txt', 'con', 'php')")
    parser.add_argument("-silent", action="store_true", help="Suppress banner")

    args = parser.parse_args()

    if not args.silent:
        print_banner()

    START_TIME = time.time()

    token = args.t or os.environ.get('GITHUB_TOKEN')

    if token and token.startswith('='):
        token = token[1:]

    if not token:
        print(f"[{Colors.ORANGE}WRN{Colors.RESET}] No GitHub token provided. Rate limits will be restrictive.")
        print(f"[{Colors.CYAN}INF{Colors.RESET}] Use -t flag or set GITHUB_TOKEN environment variable\n")

    results = search_github_api(args.s, token, args.m, args.e)

    elapsed = time.time() - START_TIME

    if results:
        if args.o:
            save_results(results, args.o)
        else:
            for word in sorted(results):
                print(word)

    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Search finished {Colors.DIM}({elapsed:.2f}s time elapsed){Colors.RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
        print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Interrupted by user")
        sys.exit(0)
