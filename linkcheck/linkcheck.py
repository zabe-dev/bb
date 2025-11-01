#!/usr/bin/env python3

import argparse
import json
import re
import signal
import sys
import threading
import time
import warnings
from urllib.parse import urljoin

import requests
import tldextract
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

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
        self.paused = False
        self.lock = threading.Lock()

    def spin(self):
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()

        idx = 0
        while self.running:
            with self.lock:
                if not self.paused:
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

    def pause(self):
        with self.lock:
            self.paused = True
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()

    def resume(self):
        with self.lock:
            self.paused = False

def signal_handler(signum, frame):
    global INTERRUPTED
    INTERRUPTED = True
    sys.stdout.write('\033[?25h')
    sys.stdout.flush()
    elapsed = (time.time() - START_TIME) if START_TIME else 0
    print(f"\n\n[{Colors.ORANGE}WRN{Colors.RESET}] Crawl interrupted {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def print_banner():
    print(rf"""{Colors.CYAN}
 _ _       _        _               _
| (_)_ __ | | _____| |__   ___  ___| | __
| | | '_ \| |/ / __| '_ \ / _ \/ __| |/ /
| | | | | |   < (__| | | |  __/ (__|
|_|_|_| |_|_|\_\___|_| |_|\___|\___|_|\_\
{Colors.RESET}
{Colors.DIM}    Broken Link Crawler v{VERSION}{Colors.RESET}
""")

def get_full_domain(url):
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"

def check_link(url, source_page, link_text, headers, skip_facebook, broken_links, stats):
    if skip_facebook and "facebook.com" in url:
        return
    if url.startswith("javascript:"):
        return

    try:
        response = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        status_code = response.status_code
        final_url = response.url

        stats['checked'] += 1

        if status_code == 403 or ("facebook.com" in url and status_code == 400):
            return

        if not (200 <= status_code < 400):
            broken_links.append({
                'url': final_url,
                'status_code': status_code,
                'source_page': source_page,
                'link_text': link_text
            })
            stats['broken'] += 1

    except requests.RequestException:
        pass

def fetch_robots_txt(base_url, headers):
    spinner = Spinner("Fetching robots.txt...")
    spinner.start()

    robots_txt_url = urljoin(base_url, '/robots.txt')
    try:
        response = requests.get(robots_txt_url, headers=headers, timeout=5)
        spinner.stop()

        if response.status_code == 200:
            urls = re.findall(r"Sitemap:\s*(\S+)", response.text, re.IGNORECASE)
            urls += re.findall(r"Allow:\s*(\S+)", response.text, re.IGNORECASE)
            urls += re.findall(r"Disallow:\s*(\S+)", response.text, re.IGNORECASE)

            if urls:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Found {len(urls)} URLs in robots.txt")
                return urls
            else:
                print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] Skipping robots.txt (no URLs found)")
                return []
        else:
            print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] Skipping robots.txt (not found)")
            return []
    except requests.RequestException:
        spinner.stop()
        print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] Skipping robots.txt (failed to fetch)")
        return []

def crawl_and_check_links(base_url, max_depth=3, show_url=False, spinner=None):
    headers = {
        "Accept-Encoding": "identity; q=1",
        "Connection": "Keep-Alive",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    visited = set()
    skip_facebook = False
    broken_links = []
    base_domain = get_full_domain(base_url)

    stats = {
        'crawled': 0,
        'checked': 0,
        'broken': 0
    }

    def crawl(url, depth=0):
        nonlocal skip_facebook

        if INTERRUPTED:
            return

        if url in visited or depth > max_depth:
            return

        visited.add(url)
        stats['crawled'] += 1

        try:
            response = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
            if response.status_code != 200:
                return

            soup = BeautifulSoup(response.text, "lxml")
            for link in soup.find_all("a", href=True):
                if INTERRUPTED:
                    return

                href = link.get("href")
                link_text = link.text.strip() or "[No text]"
                full_url = urljoin(url, href)

                link_domain = get_full_domain(full_url)

                if "facebook.com" in full_url and not skip_facebook:
                    try:
                        fb_response = requests.get(full_url, headers=headers, timeout=5, allow_redirects=True)
                        if fb_response.status_code == 400:
                            skip_facebook = True
                            if spinner:
                                spinner.pause()
                            print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] Skipping facebook links (400)")
                            if spinner:
                                spinner.resume()
                    except requests.RequestException:
                        pass

                if link_domain != base_domain:
                    check_link(full_url, url, link_text, headers, skip_facebook, broken_links, stats)
                elif not href.endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.xml')) and not href.startswith(('mailto:', 'tel:', '#')):
                    crawl(full_url, depth + 1)

        except requests.RequestException:
            pass

    urls_from_robots = fetch_robots_txt(base_url, headers)

    if show_url:
        spinner_msg = f"Crawling {base_url}..."
    else:
        spinner_msg = "Crawling target site..."

    if not spinner:
        spinner = Spinner(spinner_msg)
        spinner.start()
    else:
        spinner.message = spinner_msg

    if urls_from_robots:
        for url in urls_from_robots:
            if INTERRUPTED:
                break
            full_url = urljoin(base_url, url)
            crawl(full_url)
    else:
        crawl(base_url)

    spinner.stop()

    return broken_links, stats

def save_json_output(output_file, base_url, broken_links, stats, elapsed):
    spinner = Spinner("Saving JSON output...")
    spinner.start()

    try:
        output_data = {
            'target': base_url,
            'scan_time': elapsed,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'statistics': {
                'pages_crawled': stats['crawled'],
                'links_checked': stats['checked'],
                'broken_links_found': stats['broken']
            },
            'broken_links': broken_links
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        spinner.stop()
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Saved to {output_file}")
        return True
    except Exception as e:
        spinner.stop()
        print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to save: {e}")
        return False

def print_results(broken_links, stats):
    print(f"[{Colors.GREEN}SUC{Colors.RESET}] Crawl has been completed")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Pages crawled: {stats['crawled']}")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Links checked: {stats['checked']}")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Broken links: {stats['broken']}")

    if stats['broken'] > 0:
        print(f"\n{Colors.BOLD}Broken Links Summary:{Colors.RESET}")
        for link in broken_links:
            status_color = Colors.RED if link['status_code'] == 404 else Colors.ORANGE
            print(f"{status_color}[{link['status_code']}]{Colors.RESET} {link['url']}")
            print(f"  {Colors.DIM}└─ Found on: {link['source_page']}{Colors.RESET}")
            print(f"  {Colors.DIM}└─ Link text: {link['link_text']}{Colors.RESET}")

def read_targets_from_file(filepath):
    try:
        with open(filepath, 'r') as f:
            targets = [line.strip() for line in f if line.strip()]
        return targets
    except FileNotFoundError:
        print(f"[{Colors.RED}ERR{Colors.RESET}] File not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Error reading file: {e}")
        sys.exit(1)

def main():
    global START_TIME

    parser = argparse.ArgumentParser(
        description="Crawl a website and check for broken links",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-u", metavar="https://example.com",
                       help="Target URL to crawl")
    parser.add_argument("-l", metavar="targets.txt",
                       help="File containing list of target URLs (one per line)")
    parser.add_argument("-d", type=int, default=3, metavar="number",
                       help="Maximum crawl depth (default: 3)")
    parser.add_argument("-output", metavar="output.json",
                       help="Save results to JSON file")

    args = parser.parse_args()

    if not args.u and not args.l:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Either -u or -l must be specified")
        sys.exit(1)

    if args.u and args.l:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Cannot use both -u and -l options")
        sys.exit(1)

    targets = []
    if args.l:
        targets = read_targets_from_file(args.l)
    else:
        targets = [args.u]

    for target in targets:
        if not target.startswith(("http://", "https://")):
            print(f"[{Colors.RED}ERR{Colors.RESET}] URL must start with http:// or https://: {target}")
            continue

    print_banner()
    START_TIME = time.time()

    all_results = []

    for idx, target in enumerate(targets, 1):
        if not target.startswith(("http://", "https://")):
            continue

        if INTERRUPTED:
            break

        if len(targets) > 1:
            print(f"\n[{idx}/{len(targets)}] {Colors.BOLD}Scanning:{Colors.RESET} {target}\n")
        else:
            print(f"\n[{idx}/{len(targets)}] {Colors.BOLD}Scanning:{Colors.RESET} {target}\n")

        broken_links, stats = crawl_and_check_links(target, args.d, len(targets) > 1, None)

        print_results(broken_links, stats)

        all_results.append({
            'target': target,
            'broken_links': broken_links,
            'stats': stats
        })

    elapsed = time.time() - START_TIME

    if args.output:
        spinner = Spinner("Saving JSON output...")
        spinner.start()

        try:
            output_data = {
                'scan_time': elapsed,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_targets': len(all_results),
                'results': []
            }

            for result in all_results:
                output_data['results'].append({
                    'target': result['target'],
                    'statistics': {
                        'pages_crawled': result['stats']['crawled'],
                        'links_checked': result['stats']['checked'],
                        'broken_links_found': result['stats']['broken']
                    },
                    'broken_links': result['broken_links']
                })

            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)

            spinner.stop()
            print(f"[{Colors.GREEN}SUC{Colors.RESET}] Saved to {args.output}")
        except Exception as e:
            spinner.stop()
            print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to save: {e}")

    print(f"\n\n[{Colors.CYAN}INF{Colors.RESET}] Scan finished {Colors.DIM}({elapsed:.2f}s time elapsed){Colors.RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
        print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Interrupted by user")
        sys.exit(0)
