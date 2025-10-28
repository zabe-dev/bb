#!/usr/bin/env python3

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

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

class Config:
    REQUEST_TIMEOUT = 10
    MAX_WORKERS = 20
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cachescan/1.0)"}

def signal_handler(signum, frame):
    global INTERRUPTED
    INTERRUPTED = True
    sys.stdout.write('\033[?25h')
    sys.stdout.flush()
    elapsed = (time.time() - START_TIME) if START_TIME else 0
    print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Scan interrupted {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def print_banner():
    print(rf"""{Colors.CYAN}
               _
  ___ __ _  __| |__   ___  ___  ___ __ _ _ __
 / __/ _` |/ _` '_ \ / _ \/ __|/ __/ _` | '_ \
| (_| (_| | (_| | | |  __/\__ \ (_| (_| | | | |
 \___\__,_|\__,_| |_|\___||___/\___\__,_|_| |_|
{Colors.RESET}
{Colors.DIM}     HTTP Cache Header Analyzer v{VERSION}{Colors.RESET}
""")

def load_file(path):
    try:
        with open(path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def parse_headers_file(filepath):
    headers = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    headers.append(line)
        return headers
    except FileNotFoundError:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Headers file not found: {filepath}")
        return []

def crawl_with_katana(target, temp_file, headers=None):
    cmd = ["katana", "-u", target, "-silent", "-o", temp_file]

    if headers:
        for header in headers:
            cmd.extend(["-H", header])

    try:
        spinner = Spinner("Crawling target site...")
        spinner.start()

        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        while process.poll() is None:
            time.sleep(0.3)

        spinner.stop()

        if process.returncode == 0 and os.path.exists(temp_file):
            urls = load_file(temp_file)
            print(f"[{Colors.GREEN}SUC{Colors.RESET}] Found {len(urls)} URLs from crawling")
            return urls
        else:
            print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to crawl target site")
            return []

    except FileNotFoundError:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Katana not installed")
        return []
    except Exception as e:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Error: {e}")
        return []

def get_cache_headers(response):
    cache_headers = {
        'Cache-Control': response.headers.get('Cache-Control', 'Not Set'),
        'Expires': response.headers.get('Expires', 'Not Set'),
        'ETag': response.headers.get('ETag', 'Not Set'),
        'Last-Modified': response.headers.get('Last-Modified', 'Not Set'),
        'Pragma': response.headers.get('Pragma', 'Not Set'),
        'Age': response.headers.get('Age', 'Not Set'),
        'Vary': response.headers.get('Vary', 'Not Set'),
        'X-Cache': response.headers.get('X-Cache', 'Not Set'),
        'CF-Cache-Status': response.headers.get('CF-Cache-Status', 'Not Set'),
    }
    return cache_headers

def parse_max_age(cache_control):
    if 'max-age=' in cache_control.lower():
        try:
            parts = cache_control.lower().split('max-age=')[1].split(',')[0].strip()
            return int(parts)
        except:
            return None
    return None

def is_cacheable(cache_headers):
    cache_control = cache_headers.get('Cache-Control', '').lower()
    pragma = cache_headers.get('Pragma', '').lower()

    if 'no-store' in cache_control:
        return False, 'no-store directive (never cache)'

    if 'private' in cache_control:
        return False, 'private directive (not cacheable by shared caches)'

    if 'no-cache' in cache_control or 'no-cache' in pragma:
        if cache_headers.get('ETag') != 'Not Set' or cache_headers.get('Last-Modified') != 'Not Set':
            return True, 'no-cache with validation (must-revalidate)'
        return False, 'no-cache without validation headers'

    if 'must-revalidate' in cache_control or 'proxy-revalidate' in cache_control:
        if 'max-age' in cache_control:
            max_age = parse_max_age(cache_control)
            if max_age and max_age > 0:
                return True, f'max-age={max_age}s (must-revalidate)'
        if cache_headers.get('Expires') != 'Not Set':
            return True, 'Expires header (must-revalidate)'
        return False, 'must-revalidate without expiration'

    if 'max-age' in cache_control:
        max_age = parse_max_age(cache_control)
        if max_age and max_age > 0:
            if 'public' in cache_control:
                return True, f'max-age={max_age}s (public)'
            return True, f'max-age={max_age}s'
        elif max_age == 0:
            return False, 'max-age=0 (no cache)'

    if cache_headers.get('Expires') != 'Not Set':
        return True, 'Expires header present'

    if cache_headers.get('ETag') != 'Not Set' or cache_headers.get('Last-Modified') != 'Not Set':
        return True, 'Conditional caching (ETag/Last-Modified)'

    return False, 'No cache headers'

def analyze_url(url):
    try:
        response = requests.get(url, timeout=Config.REQUEST_TIMEOUT, headers=Config.HEADERS, allow_redirects=True)
        cache_headers = get_cache_headers(response)
        cacheable, reason = is_cacheable(cache_headers)

        return {
            'url': url,
            'status_code': response.status_code,
            'cacheable': cacheable,
            'reason': reason,
            'content_type': response.headers.get('Content-Type', 'Unknown'),
            'headers': cache_headers
        }
    except Exception as e:
        return {
            'url': url,
            'status_code': 'Error',
            'cacheable': False,
            'reason': f'Request failed: {str(e)}',
            'content_type': 'Unknown',
            'headers': {}
        }

def analyze_urls(urls):
    results = []

    spinner = Spinner(f"Analyzing cache headers for {len(urls)} URLs")
    spinner.start()

    with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
        results = list(executor.map(analyze_url, urls))

    spinner.stop()

    return results

def filter_cacheable(results):
    return [r for r in results if r['cacheable']]

def print_summary(cacheable_count, total_count, output_file):
    percentage = (cacheable_count / total_count * 100) if total_count > 0 else 0

    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Analysis complete")
    print(f"[{Colors.GREEN}+{Colors.RESET}] Cacheable URLs: {cacheable_count}/{total_count} ({percentage:.1f}%)")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Results saved to: {output_file}")

    elapsed = time.time() - START_TIME
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Scan finished {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}\n")

def main():
    global START_TIME

    parser = argparse.ArgumentParser(description='HTTP Cache Header Analyzer')
    parser.add_argument('-d', required=True, metavar="example.com", help='Target domain')
    parser.add_argument('-H', dest='headers', action='append', metavar="header:value", help='Custom headers for crawling')
    parser.add_argument('-output', required=True, metavar="results.json", help='Output JSON file')

    args = parser.parse_args()

    print_banner()
    START_TIME = time.time()

    target = args.d.strip()
    output_file = args.output.strip()

    headers = []
    if args.headers:
        for header in args.headers:
            if os.path.isfile(header):
                headers.extend(parse_headers_file(header))
            else:
                headers.append(header)

    temp_file = ".urls_temp.txt"

    urls = crawl_with_katana(target, temp_file, headers if headers else None)

    if not urls:
        print(f"[{Colors.RED}ERR{Colors.RESET}] No URLs found to analyze")
        return

    print()

    results = analyze_urls(urls)

    cacheable_results = filter_cacheable(results)

    save_json(output_file, cacheable_results)

    if os.path.exists(temp_file):
        os.remove(temp_file)

    print_summary(len(cacheable_results), len(results), output_file)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
        print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Interrupted by user")
        sys.exit(0)
