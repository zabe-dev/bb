#!/usr/bin/env python3

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import requests

VERSION = "1.0"
START_TIME = None
INTERRUPTED = False
LOADING_ACTIVE = False

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
    REQUEST_DELAY = 1.5
    MAX_RETRIES = 3
    RATE_LIMIT_PAUSE = 300
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; wayplus/1.0)"}

    JWT_REGEX = re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}')
    JUICY_FIELDS = ["email", "username", "password", "api_key", "access_token",
                    "session_id", "role", "scope"]

    SECRET_PARAMS = re.compile(
        r'[?&](code|token|ticket|key|secret|password|pass|pwd|auth|session|sid|jwt|bearer|'
        r'access_token|refresh_token|api_key|apikey|client_secret|private_key|oauth|callback|'
        r'redirect|redirect_uri|state|nonce)=',
        re.IGNORECASE
    )

    API_PATTERNS = re.compile(
        r'^https?://api\.|^https?://[^/]+/api(/v[0-9]+)?|/graphql|/graphiql|/playground|'
        r'/api/v[0-9]+|/v[1-6]/graphql|\.api\.',
        re.IGNORECASE
    )

    STATIC_EXTENSIONS = re.compile(
        r'\.(js|css|txt|json|xml|pdf|doc|docx|xls|xlsx|ppt|pptx|zip|tar|gz|rar|7z|'
        r'exe|dmg|pkg|deb|rpm|iso|img|svg|ico|woff|woff2|ttf|eot|otf|mp3|mp4|wav|'
        r'avi|mov|wmv|flv|webm|ogg|png|jpg|jpeg|gif|bmp|tiff|webp)(\?.*)?$',
        re.IGNORECASE
    )

    GF_PATTERNS = ["idor", "lfi", "rce", "redirect", "sqli", "ssrf", "ssti", "xss"]

    DEFAULT_EXTENSIONS = [".zip", ".tar.gz", ".rar", ".sql", ".bak", ".7z", ".gz"]
    LISTING_PATTERNS = ["Index of /", "Parent Directory", "Directory listing",
                       "Last modified", "Name</a>"]

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
__      ____ _ _   _ _ __ | |_   _ ___
\ \ /\ / / _` | | | | '_ \| | | | / __|
 \ V  V / (_| | |_| | |_) | | |_| \__ \
  \_/\_/ \__,_|\__, | .__/|_|\__,_|___/
               |___/|_|
{Colors.RESET}
{Colors.DIM}        Wayback URL Analyzer v{VERSION}{Colors.RESET}
""")


def load_file(path, default=None):
    try:
        with open(path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        if default:
            return default
        return []

def save_file(path, lines):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        f.write('\n'.join(lines))

def retry_request(url, timeout=30):
    for attempt in range(Config.MAX_RETRIES):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 429:
                time.sleep(Config.RATE_LIMIT_PAUSE)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException:
            if attempt < Config.MAX_RETRIES - 1:
                time.sleep(Config.REQUEST_DELAY * (2 ** attempt))
    return None

def fetch_waymore_urls(target, output_dir):
    output_file = f"{output_dir}/{target}_urls.txt"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cmd = ["waymore", "-mode", "U", "-t", "5", "-p", "2", "-lr", "60",
           "-r", "5", "-oU", output_file, "-i", target]

    try:
        print()
        spinner = Spinner("Fetching URLs from archives...")
        spinner.start()

        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)

        while process.poll() is None:
            time.sleep(0.3)

        spinner.stop()

        if process.returncode == 0 and os.path.exists(output_file):
            urls = load_file(output_file)
            print(f"[{Colors.GREEN}SUC{Colors.RESET}] Retrieved {len(urls)} URLs")
            return urls, output_file
        else:
            print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to fetch URLs")
            return [], None

    except FileNotFoundError:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Waymore not installed. Run `{Colors.DIM}pipx install git+https://github.com/xnl-h4ck3r/waymore.git{Colors.RESET}` to install.")
        return [], None
    except Exception as e:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Error: {e}")
        return [], None

def crawl_with_katana(target, output_dir):
    output_file = f"{output_dir}/{target}_katana.txt"

    target_url = target if target.startswith(('http://', 'https://')) else f"https://{target}"

    cmd = ["katana", "-u", target_url, "-retry", "3", "-jc", "-o", output_file]

    try:
        spinner = Spinner("Crawling site with Katana...")
        spinner.start()

        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)

        while process.poll() is None:
            time.sleep(0.3)

        spinner.stop()

        if process.returncode == 0 and os.path.exists(output_file):
            urls = load_file(output_file)
            print(f"[{Colors.GREEN}SUC{Colors.RESET}] Crawled {len(urls)} URLs")
            return urls, output_file
        else:
            print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to crawl with Katana")
            return [], None

    except FileNotFoundError:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Katana not installed. Run `{Colors.DIM}CGO_ENABLED=1 go install github.com/projectdiscovery/katana/cmd/katana@latest{Colors.RESET}` to install.")
        return [], None
    except Exception as e:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Error: {e}")
        return [], None

def gf_pattern_match(urls_file, pattern, output_dir, target):
    try:
        output_path = f"{output_dir}/{target}_{pattern}.txt"

        with open(urls_file, 'r') as f:
            result = subprocess.run(['gf', pattern], stdin=f, capture_output=True, text=True)

        if result.returncode == 0 and result.stdout.strip():
            matched = result.stdout.strip().split('\n')
            save_file(output_path, matched)
            return matched

        return []

    except FileNotFoundError:
        return []
    except Exception:
        return []

def fetch_compressed_files_urls(target, output_dir, extensions=None):
    extensions = extensions or Config.DEFAULT_EXTENSIONS

    archive_url = f'https://web.archive.org/cdx/search/cdx?url=*.{target}/*&output=txt&fl=original&collapse=urlkey&page=/'

    spinner = Spinner("Fetching archive data")
    spinner.start()
    response = retry_request(archive_url, timeout=60)
    spinner.stop()

    if not response:
        return []

    urls = response.text.splitlines()

    all_urls = []
    for url in urls:
        if any(url.lower().endswith(ext.lower()) for ext in extensions):
            all_urls.append(url)

    if all_urls:
        compressed_path = f"{output_dir}/{target}_compressed.txt"
        save_file(compressed_path, all_urls)

    return all_urls

def extract_jwt_from_url(url):
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    for values in query_params.values():
        for value in values:
            val = unquote(value)
            if re.match(Config.JWT_REGEX, val):
                return val

    decoded_url = unquote(url)
    match = Config.JWT_REGEX.search(decoded_url)
    return match.group(0) if match else None

def check_url_status(url):
    try:
        resp = requests.head(url, headers=Config.HEADERS,
                           allow_redirects=True, timeout=10)
        return url if resp.status_code in [200, 301, 302] else None
    except requests.exceptions.RequestException:
        return None

def analyze_jwts_from_urls(urls, output_dir, target):
    jwt_map = {url: token for url in urls if (token := extract_jwt_from_url(url))}

    if not jwt_map:
        return 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        live_urls = list(filter(None, executor.map(check_url_status, jwt_map.keys())))

    if not live_urls:
        return 0

    results = {}
    for url in live_urls:
        token = jwt_map[url]
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            juicy = {k: v for k, v in decoded.items() if k in Config.JUICY_FIELDS}
            results[url] = {"jwt": token, "decoded": decoded, "juicy": juicy}
        except Exception:
            continue

    if results:
        jwt_path = f"{output_dir}/{target}_jwt.json"
        with open(jwt_path, "w") as f:
            json.dump(results, f, indent=2)
        return len(results)

    return 0

def extract_subdomains_from_urls(urls, root_domain=None):
    subdomains = set()
    for url in urls:
        if match := re.search(r"https?://([a-zA-Z0-9.-]+)", url):
            domain = match.group(1).lower().split(':')[0]
            if not root_domain or domain.endswith(root_domain):
                subdomains.add(domain)

    return list(subdomains)

def extract_parameters(urls):
    param_regex = re.compile(r'\?([^#]+)')
    seen = set()
    results = []

    for url in urls:
        if match := param_regex.search(url):
            param_segment = match.group(1)
            param_pairs = [p.split('=')[0] for p in param_segment.split('&') if '=' in p]

            if param_pairs:
                key = tuple(sorted(set(param_pairs)))
                if (key, url) not in seen:
                    seen.add((key, url))
                    results.append(url)

    return results

def scan_for_listings(domain, output_dir, threads=10):
    archive_url = f"https://web.archive.org/cdx/search/cdx?url=*.{domain}/*&output=txt&fl=original&collapse=urlkey"

    spinner = Spinner("Fetching Wayback URLs")
    spinner.start()
    response = retry_request(archive_url, timeout=15)
    spinner.stop()

    if not response:
        return []

    urls = response.text.splitlines()
    paths = {urlparse(url).path for url in urls
             if urlparse(url).hostname == domain and urlparse(url).path and urlparse(url).path != "/"}

    def check_listing(path):
        for scheme in ["http", "https"]:
            full_url = f"{scheme}://{domain}{path}"
            try:
                r = requests.get(full_url, timeout=5)
                if r.status_code == 200 and any(p in r.text for p in Config.LISTING_PATTERNS):
                    return full_url
            except:
                continue
        return None

    listings = []
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for result in executor.map(check_listing, paths):
            if result:
                listings.append(result)

    if listings:
        output_path = f"{output_dir}/{domain}_dir_listings.txt"
        save_file(output_path, listings)

    return listings

def find_keyword(urls, keyword):
    matches = [u for u in urls if keyword.lower() in u.lower()]
    return matches

def extract_secret_urls(urls, output_dir, target):
    secret = [url for url in urls if Config.SECRET_PARAMS.search(url)]

    if secret:
        output_path = f"{output_dir}/{target}_secrets.txt"
        save_file(output_path, secret)

    return secret

def extract_api_urls(urls, output_dir, target):
    api_urls = [url for url in urls
                if Config.API_PATTERNS.search(url) and not Config.STATIC_EXTENSIONS.search(url)]

    if api_urls:
        output_path = f"{output_dir}/{target}_apis.txt"
        save_file(output_path, api_urls)

    return api_urls

def extract_static_urls(urls, output_dir, target):
    static_urls = [url for url in urls if Config.STATIC_EXTENSIONS.search(url)]

    if static_urls:
        output_path = f"{output_dir}/{target}_static.txt"
        save_file(output_path, static_urls)

    return static_urls

def run_automated_analysis(urls, urls_file, target, output_dir):
    results = {}

    spinner = Spinner("Extracting subdomains")
    spinner.start()
    subdomains = extract_subdomains_from_urls(urls, target)
    spinner.stop()
    if subdomains:
        save_file(f"{output_dir}/{target}_subdomains.txt", subdomains)
        results["subdomains"] = len(subdomains)
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Subdomains: {len(subdomains)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Subdomains: 0 found")

    spinner = Spinner("Extracting parameters")
    spinner.start()
    params = extract_parameters(urls)
    spinner.stop()
    if params:
        save_file(f"{output_dir}/{target}_parameters.txt", params)
        results["parameters"] = len(params)
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Parameters: {len(params)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Parameters: 0 found")

    spinner = Spinner("Searching for Secret URLs")
    spinner.start()
    secret = extract_secret_urls(urls, output_dir, target)
    spinner.stop()
    results["secret"] = len(secret)
    if secret:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Secret URLs: {len(secret)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Secret URLs: 0 found")

    spinner = Spinner("Extracting API endpoints")
    spinner.start()
    apis = extract_api_urls(urls, output_dir, target)
    spinner.stop()
    results["apis"] = len(apis)
    if apis:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] API endpoints: {len(apis)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] API endpoints: 0 found")

    spinner = Spinner("Extracting static files")
    spinner.start()
    static_files = extract_static_urls(urls, output_dir, target)
    spinner.stop()
    results["static_files"] = len(static_files)
    if static_files:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Static files: {len(static_files)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Static files: 0 found")

    spinner = Spinner("Searching for JSON URLs")
    spinner.start()
    json_urls = find_keyword(urls, "json")
    spinner.stop()
    if json_urls:
        save_file(f"{output_dir}/{target}_json.txt", json_urls)
        results["json"] = len(json_urls)
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] JSON URLs: {len(json_urls)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] JSON URLs: 0 found")

    spinner = Spinner("Searching for config URLs")
    spinner.start()
    config_urls = find_keyword(urls, "conf")
    spinner.stop()
    if config_urls:
        save_file(f"{output_dir}/{target}_config.txt", config_urls)
        results["config"] = len(config_urls)
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Config URLs: {len(config_urls)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Config URLs: 0 found")

    spinner = Spinner("Analyzing JWT tokens")
    spinner.start()
    jwt_count = analyze_jwts_from_urls(urls, output_dir, target)
    spinner.stop()
    results["jwt"] = jwt_count
    if jwt_count:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] JWT tokens: {jwt_count} analyzed")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] JWT tokens: 0 found")

    spinner = Spinner("Searching for compressed files")
    spinner.start()
    compressed = fetch_compressed_files_urls(target, output_dir, load_file("extensions.txt", Config.DEFAULT_EXTENSIONS))
    spinner.stop()
    results["compressed"] = len(compressed)
    if compressed:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Compressed files: {len(compressed)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Compressed files: 0 found")

    for pattern in Config.GF_PATTERNS:
        spinner = Spinner(f"Scanning for {pattern.upper()} patterns")
        spinner.start()
        matched = gf_pattern_match(urls_file, pattern, output_dir, target)
        spinner.stop()
        results[pattern] = len(matched)
        if matched:
            print(f"[{Colors.GREEN}SUC{Colors.RESET}] {pattern.upper()} patterns: {len(matched)} matches")
        else:
            print(f"[{Colors.RED}FAIL{Colors.RESET}] {pattern.upper()} patterns: 0 found")

    spinner = Spinner("Scanning for directory listings")
    spinner.start()
    listings = scan_for_listings(target, output_dir)
    spinner.stop()
    results["dir_listings"] = len(listings)
    if listings:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Directory listings: {len(listings)} found")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Directory listings: 0 found")

    return results

def print_summary(results, output_dir):
    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Results saved to: {output_dir}")

    elapsed = time.time() - START_TIME
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Scan finished {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}\n")

def main():
    global START_TIME

    parser = argparse.ArgumentParser(description='Wayback URL Analyzer')
    parser.add_argument('-d', required=True, metavar="example.com", help='Target domain')
    parser.add_argument('-output', required=True, metavar="output_dir/",  help='Output directory')

    args = parser.parse_args()

    print_banner()
    START_TIME = time.time()

    target = args.d.strip()
    output_dir = args.output.strip()

    urls, urls_file = fetch_waymore_urls(target, output_dir)
    if not urls:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to fetch URLs")
        return

    katana_urls, katana_file = crawl_with_katana(target, output_dir)

    if katana_urls:
        all_urls = list(set(urls + katana_urls))
        combined_file = f"{output_dir}/{target}_combined.txt"
        save_file(combined_file, all_urls)
        print(f"[{Colors.CYAN}INF{Colors.RESET}] Total unique URLs: {len(all_urls)}")
        urls = all_urls
        urls_file = combined_file

    results = run_automated_analysis(urls, urls_file, target, output_dir)

    print_summary(results, output_dir)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
        print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Interrupted by user")
        sys.exit(0)
