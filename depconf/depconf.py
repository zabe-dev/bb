#!/usr/bin/env python3

import argparse
import atexit
import concurrent.futures
import json
import os
import re
import signal
import sys
import termios
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
INTERRUPTED = False
SILENT_MODE = False
START_TIME = None
OLD_TERM_SETTINGS = None

class Colors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GREEN = '\033[92m'
    MAGENTA = '\033[95m'

REPO_METADATA_CACHE = {}

def cleanup():
    global OLD_TERM_SETTINGS
    if OLD_TERM_SETTINGS is not None:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, OLD_TERM_SETTINGS)
        except:
            pass

def signal_handler(signum, frame):
    global INTERRUPTED, START_TIME
    INTERRUPTED = True
    print(f"[{Colors.YELLOW}WRN{Colors.RESET}] Scan interrupted by user")
    cleanup()
    elapsed_time = (time.time() - START_TIME) if START_TIME is not None else 0
    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Scan finished {Colors.DIM}({elapsed_time:.3f}s elapsed time){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

def print_banner():
    if SILENT_MODE:
        return

    banner = rf"""
{Colors.CYAN}      _                             __
  __| | ___ _ __   ___ ___  _ __  / _|
 / _` |/ _ \ '_ \ / __/ _ \| '_ \| |_
| (_| |  __/ |_) | (_| (_) | | | |  _|
 \__,_|\___| .__/ \___\___/|_| |_|_|
           |_|                        {Colors.RESET}

{Colors.DIM}        Dependency Confusion Scanner v1.0{Colors.RESET}
"""
    print(banner)

def get_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

def get_repo_metadata(repo_url: str) -> Optional[Dict]:
    if repo_url in REPO_METADATA_CACHE:
        return REPO_METADATA_CACHE[repo_url]

    try:
        parts = repo_url.rstrip("/").replace(".git", "").split("/")
        owner = parts[-2]
        repo_name = parts[-1]

        url = f"https://api.github.com/repos/{owner}/{repo_name}"
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code == 200:
            data = response.json()
            metadata = {
                "fork": data.get("fork", False),
                "private": data.get("private", False),
                "archived": data.get("archived", False),
            }
            REPO_METADATA_CACHE[repo_url] = metadata
            return metadata
    except:
        pass

    return None

def format_repo_type(metadata: Optional[Dict], failed: bool = False) -> str:
    badges = []

    if failed:
        badges.append(f"[{Colors.RED}failed{Colors.RESET}]")

    if metadata is None:
        badges.append(f"[{Colors.DIM}unknown{Colors.RESET}]")
        return " ".join(badges)

    if metadata.get("private"):
        badges.append(f"[{Colors.MAGENTA}private{Colors.RESET}]")

    if metadata.get("fork"):
        badges.append(f"[{Colors.YELLOW}fork{Colors.RESET}]")
    else:
        badges.append(f"[{Colors.GREEN}origin{Colors.RESET}]")

    if metadata.get("archived"):
        badges.append(f"[{Colors.CYAN}archived{Colors.RESET}]")

    return " ".join(badges)

def get_org_repos(org: str, include_forks: bool = True) -> List[Dict]:
    repos = []
    page = 1

    while True:
        if INTERRUPTED:
            return repos

        url = f"https://api.github.com/orgs/{org}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to fetch org repos: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for repo in data:
            if include_forks or not repo.get("fork", False):
                repo_info = {
                    "url": repo["clone_url"],
                    "fork": repo.get("fork", False),
                    "private": repo.get("private", False),
                    "archived": repo.get("archived", False),
                }
                repos.append(repo_info)

                REPO_METADATA_CACHE[repo["clone_url"]] = {
                    "fork": repo_info["fork"],
                    "private": repo_info["private"],
                    "archived": repo_info["archived"],
                }

        page += 1

    return repos

def get_org_members(org: str) -> List[str]:
    members = []
    page = 1

    while True:
        if INTERRUPTED:
            return members

        url = f"https://api.github.com/orgs/{org}/members?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to fetch org members: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for member in data:
            members.append(member["login"])

        page += 1

    return list(set(members))

def get_user_repos(username: str, include_forks: bool = True) -> List[Dict]:
    repos = []
    page = 1

    while True:
        if INTERRUPTED:
            return repos

        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"[{Colors.RED}ERR{Colors.RESET}] Failed to fetch repos for {username}: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for repo in data:
            if include_forks or not repo.get("fork", False):
                repo_info = {
                    "url": repo["clone_url"],
                    "fork": repo.get("fork", False),
                    "private": repo.get("private", False),
                    "archived": repo.get("archived", False),
                }
                repos.append(repo_info)

                REPO_METADATA_CACHE[repo["clone_url"]] = {
                    "fork": repo_info["fork"],
                    "private": repo_info["private"],
                    "archived": repo_info["archived"],
                }

        page += 1

    return repos

class DepConfScanner:
    def __init__(self, threads=10):
        self.threads = threads
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.wp_plugin_svn_url = "https://plugins.svn.wordpress.org/{}/"

    def fetch_url(self, url):
        try:
            resp = self.session.get(url, timeout=10, allow_redirects=True)
            return resp.text if resp.status_code == 200 else None
        except:
            return None

    def is_obfuscated_or_bundle(self, js_content, url):
        if not js_content or len(js_content) < 100:
            return True

        if len(js_content) > 500000:
            return True

        url_lower = url.lower()
        skip_patterns = [
            'bundle', 'chunk', 'vendor', 'webpack', 'runtime',
            '.min.js', 'polyfill', 'analytics', 'gtm', 'google',
            'facebook', 'tracking', 'ads'
        ]
        if any(pattern in url_lower for pattern in skip_patterns):
            return True

        sample = js_content[:5000]

        lines = sample.split('\n')
        if len(lines) > 0:
            avg_line_length = sum(len(line) for line in lines) / len(lines)
            if avg_line_length > 500:
                return True

        very_long_lines = sum(1 for line in lines if len(line) > 1000)
        if very_long_lines > len(lines) * 0.3:
            return True

        obfuscation_indicators = [
            r'_0x[a-f0-9]{4,}',
            r'\\x[0-9a-f]{2}',
            r'eval\s*\(',
            r'Function\s*\(',
            r'\\u[0-9a-f]{4}',
        ]

        indicator_count = 0
        for pattern in obfuscation_indicators:
            if len(re.findall(pattern, sample)) > 5:
                indicator_count += 1

        if indicator_count >= 2:
            return True

        if sample.count(';') < 5 and len(sample) > 1000:
            return True

        return False

    def extract_js_urls(self, html, base_url):
        js_urls = set()
        script_tags = re.findall(r'<script[^>]+src=["\'](.*?)["\']', html, re.IGNORECASE)
        for src in script_tags:
            js_url = urljoin(base_url, src)
            if js_url.startswith('http'):
                js_urls.add(js_url)
        return js_urls

    def extract_wp_plugins(self, html):
        plugins = set()
        matches = re.findall(r"wp-content/plugins/([a-zA-Z0-9\-_]+)/", html)
        plugins.update(m.lower() for m in matches)
        return plugins

    def check_wp_plugin(self, plugin_slug):
        check_url = self.wp_plugin_svn_url.format(plugin_slug)
        try:
            resp = self.session.head(check_url, timeout=7)
            return resp.status_code != 404
        except:
            return True

    def extract_packages_from_js(self, js_content):
        packages = {}

        npm_patterns = [
            r'require\(["\']([a-zA-Z0-9@/_-]+)["\']\)',
            r'from\s+["\']([a-zA-Z0-9@/_-]+)["\']',
            r'import\s+.*?\s+from\s+["\']([a-zA-Z0-9@/_-]+)["\']',
        ]

        for pattern in npm_patterns:
            matches = re.findall(pattern, js_content)
            for match in matches:
                if match.startswith('.') or match.startswith('/') or 'http' in match:
                    continue

                pkg = match.split('/')[0]

                if not pkg or len(pkg) < 2:
                    continue

                if pkg.startswith('@'):
                    if '/' in match:
                        pkg = '/'.join(match.split('/')[:2])
                    else:
                        continue

                is_valid, confidence = self.is_valid_package_name(pkg)
                if is_valid:
                    if pkg not in packages or packages[pkg] < confidence:
                        packages[pkg] = confidence

        return packages

    def is_valid_package_name(self, pkg):
        if not pkg or len(pkg) < 2:
            return False, 0

        confidence = 100

        if pkg.startswith('@'):
            if '/' not in pkg:
                return False, 0
            parts = pkg.split('/')
            if len(parts) != 2 or not parts[1]:
                return False, 0

        if re.match(r'^[a-zA-Z@]', pkg) is None:
            return False, 0

        invalid_chars = set('!#$%^&*()+={}[]|\\:;"\'<>,.?~ ')
        if any(c in invalid_chars for c in pkg):
            return False, 0

        common_false_positives = ['react', 'vue', 'angular', 'lodash', 'jquery',
                                   'moment', 'axios', 'express', 'webpack', 'babel']
        if pkg.lower() in common_false_positives:
            return False, 0

        if len(pkg) < 4:
            confidence -= 20

        if '-' not in pkg and not pkg.startswith('@'):
            confidence -= 10

        if pkg.startswith('@') and '/' in pkg:
            confidence += 10

        clean_pkg = pkg.replace('@', '').replace('/', '')
        if re.match(r'^[a-z0-9\-]+$', clean_pkg):
            confidence += 5

        return True, confidence

    def scan_github_repo(self, repo_url):
        parts = urlparse(repo_url).path.strip('/').split('/')
        if len(parts) < 2:
            return {}

        owner, repo = parts[0], parts[1]
        api_url = f'https://api.github.com/repos/{owner}/{repo}/contents'

        packages = {}
        files_to_check = ['package.json', 'requirements.txt', 'Gemfile', 'setup.py']

        for filename in files_to_check:
            if INTERRUPTED:
                return packages
            file_url = f'{api_url}/{filename}'
            try:
                resp = self.session.get(file_url, headers=get_headers(), timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if 'download_url' in data:
                        content = self.fetch_url(data['download_url'])
                        if content:
                            found_packages = self.parse_dependency_file(content, filename)
                            for pkg in found_packages:
                                packages[pkg] = 95
            except:
                pass

        return packages

    def parse_dependency_file(self, content, filename):
        packages = set()

        if filename == 'package.json':
            try:
                data = json.loads(content)
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                packages.update(deps.keys())
            except:
                pass

        elif filename == 'requirements.txt':
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    pkg = re.split('[=<>!]', line)[0].strip()
                    if pkg:
                        packages.add(pkg)

        elif filename == 'Gemfile':
            matches = re.findall(r'gem\s+["\']([^"\']+)["\']', content)
            packages.update(matches)

        return packages

    def scan_domain(self, url):
        if not url.startswith('http'):
            url = 'https://' + url

        html = self.fetch_url(url)
        if not html:
            return {'packages': {}, 'wp_plugins': set()}

        js_urls = self.extract_js_urls(html, url)
        wp_plugins = self.extract_wp_plugins(html)

        all_packages = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_url = {executor.submit(self.fetch_url, js_url): js_url for js_url in js_urls}

            for future in concurrent.futures.as_completed(future_to_url):
                if INTERRUPTED:
                    break
                js_url = future_to_url[future]
                js_content = future.result()
                if js_content:
                    if not self.is_obfuscated_or_bundle(js_content, js_url):
                        packages = self.extract_packages_from_js(js_content)
                        for pkg, conf in packages.items():
                            if pkg not in all_packages or all_packages[pkg] < conf:
                                all_packages[pkg] = conf

        return {'packages': all_packages, 'wp_plugins': wp_plugins}

    def check_npm_package(self, package_name):
        url = f'https://registry.npmjs.org/{package_name}'
        try:
            resp = self.session.get(url, timeout=5)
            return resp.status_code == 200
        except:
            return False

    def check_pypi_package(self, package_name):
        url = f'https://pypi.org/pypi/{package_name}/json'
        try:
            resp = self.session.get(url, timeout=5)
            return resp.status_code == 200
        except:
            return False

    def check_rubygems_package(self, package_name):
        url = f'https://rubygems.org/api/v1/gems/{package_name}.json'
        try:
            resp = self.session.get(url, timeout=5)
            return resp.status_code == 200
        except:
            return False

    def verify_wp_plugins(self, plugins):
        vulnerable = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_plugin = {executor.submit(self.check_wp_plugin, plugin): plugin for plugin in plugins}

            for future in concurrent.futures.as_completed(future_to_plugin):
                if INTERRUPTED:
                    break
                plugin = future_to_plugin[future]
                exists = future.result()

                if not exists:
                    vulnerable.append(plugin)

        return vulnerable

    def verify_packages(self, packages, registry='npm'):
        check_func = {
            'npm': self.check_npm_package,
            'pypi': self.check_pypi_package,
            'rubygems': self.check_rubygems_package
        }.get(registry, self.check_npm_package)

        vulnerable = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_pkg = {executor.submit(check_func, pkg): pkg for pkg in packages.keys()}

            for future in concurrent.futures.as_completed(future_to_pkg):
                if INTERRUPTED:
                    break
                pkg = future_to_pkg[future]
                exists = future.result()

                if not exists:
                    vulnerable[pkg] = packages[pkg]

        return vulnerable

def scan_repository(repo_url: str, idx: int, total: int, scanner: DepConfScanner, registry: str):
    if INTERRUPTED:
        return None

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    org_or_user = repo_url.rstrip("/").split("/")[-2]
    repo_full = f"{org_or_user}/{repo_name}"

    metadata = get_repo_metadata(repo_url)

    padding = len(str(total))
    progress = f"{Colors.DIM}[{str(idx).zfill(padding)}/{total}]{Colors.RESET}"
    repo_type = format_repo_type(metadata, failed=False)

    packages = scanner.scan_github_repo(repo_url)

    vulnerable = {}
    if packages:
        vulnerable = scanner.verify_packages(packages, registry)

    if vulnerable:
        count = f"[{Colors.RED}{len(vulnerable)} vulnerable{Colors.RESET}]"
        if not SILENT_MODE:
            print(f"{progress} {repo_type} {repo_full} {count}")
        return {"repo": repo_full, "vulnerable": vulnerable, "registry": registry}
    else:
        if not SILENT_MODE:
            print(f"{progress} {repo_type} {repo_full}")
        return None

def scan_domain_target(url: str, idx: int, total: int, scanner: DepConfScanner, registry: str):
    if INTERRUPTED:
        return None

    padding = len(str(total))
    progress = f"{Colors.DIM}[{str(idx).zfill(padding)}/{total}]{Colors.RESET}"

    result = scanner.scan_domain(url)
    packages = result['packages']
    wp_plugins = result['wp_plugins']

    vulnerable_packages = {}
    vulnerable_wp = []

    if packages:
        vulnerable_packages = scanner.verify_packages(packages, registry)

    if wp_plugins:
        vulnerable_wp = scanner.verify_wp_plugins(wp_plugins)

    total_vulns = len(vulnerable_packages) + len(vulnerable_wp)

    if total_vulns > 0:
        count = f"[{Colors.RED}{total_vulns} vulnerable{Colors.RESET}]"
        if not SILENT_MODE:
            print(f"{progress} {url} {count}")
        return {
            "url": url,
            "vulnerable": vulnerable_packages,
            "vulnerable_wp": vulnerable_wp,
            "registry": registry
        }
    else:
        if not SILENT_MODE:
            print(f"{progress} {url}")
        return None

def main():
    global SILENT_MODE, START_TIME, OLD_TERM_SETTINGS

    try:
        OLD_TERM_SETTINGS = termios.tcgetattr(sys.stdin)
        new_settings = termios.tcgetattr(sys.stdin)
        new_settings[3] = new_settings[3] & ~termios.ECHOCTL
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)
    except:
        pass

    parser = argparse.ArgumentParser(description="Dependency Confusion Scanner")
    parser.add_argument("-d", "--domain", nargs='+', help="Target domain(s) to scan")
    parser.add_argument("-org", help="GitHub organization name")
    parser.add_argument("-user", help="GitHub username")
    parser.add_argument("-repo", help="Single repository URL")
    parser.add_argument("-include-forks", action="store_true", help="Include forked repositories")
    parser.add_argument("-include-members", action="store_true", help="Include organization member repositories")
    parser.add_argument("-t", "--threads", type=int, default=10, help="Number of threads")
    parser.add_argument("--registry", choices=['npm', 'pypi', 'rubygems'], default='npm', help="Package registry to check")
    parser.add_argument("-silent", action="store_true", help="Only print scan results")

    args = parser.parse_args()

    SILENT_MODE = args.silent

    if not args.org and not args.repo and not args.user and not args.domain:
        if not SILENT_MODE:
            print(f"[{Colors.RED}ERR{Colors.RESET}] Must specify -org, -user, -repo, or -d/--domain")
        sys.exit(1)

    print_banner()

    if not GITHUB_TOKEN and (args.org or args.user or args.repo) and not SILENT_MODE:
        print(f"[{Colors.YELLOW}WRN{Colors.RESET}] GITHUB_TOKEN not set, rate limits may apply")

    scanner = DepConfScanner(threads=args.threads)
    all_targets = []
    scan_type = None

    if args.domain:
        scan_type = "domain"
        all_targets = args.domain
        if not SILENT_MODE:
            if len(all_targets) > 1:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Target domains: {Colors.BOLD}{len(all_targets)}{Colors.RESET}")
            elif len(all_targets) == 1:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Target domain: {Colors.BOLD}{all_targets[0]}{Colors.RESET}")

    else:
        scan_type = "repo"
        all_repos: Dict[str, Dict] = {}

        if args.repo:
            all_repos[args.repo] = {"url": args.repo}

        if args.org:
            if not SILENT_MODE:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Target organization: {Colors.BOLD}{args.org}{Colors.RESET}")
            org_repos = get_org_repos(args.org, args.include_forks)
            if not SILENT_MODE:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Found {Colors.BOLD}{len(org_repos)}{Colors.RESET} organization repositories")
            for repo_info in org_repos:
                all_repos[repo_info["url"]] = repo_info

            if args.include_members:
                if not SILENT_MODE:
                    print(f"[{Colors.CYAN}INF{Colors.RESET}] Fetching organization members")
                members = get_org_members(args.org)
                if not SILENT_MODE:
                    print(f"[{Colors.CYAN}INF{Colors.RESET}] Found {Colors.BOLD}{len(members)}{Colors.RESET} organization members")

                for member in members:
                    if INTERRUPTED:
                        break
                    member_repos = get_user_repos(member, args.include_forks)
                    if member_repos and not SILENT_MODE:
                        print(f"{Colors.DIM}[*]{Colors.RESET} {member}: {len(member_repos)} repositories")
                    for repo_info in member_repos:
                        all_repos[repo_info["url"]] = repo_info

        if args.user:
            if not SILENT_MODE:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Target user: {Colors.BOLD}{args.user}{Colors.RESET}")
            user_repos = get_user_repos(args.user, args.include_forks)
            if not SILENT_MODE:
                print(f"[{Colors.CYAN}INF{Colors.RESET}] Found {Colors.BOLD}{len(user_repos)}{Colors.RESET} user repositories")
            for repo_info in user_repos:
                all_repos[repo_info["url"]] = repo_info

        all_targets = sorted(list(all_repos.keys()))

    if INTERRUPTED:
        sys.exit(130)

    if not SILENT_MODE:
        target_type = "domains" if scan_type == "domain" else "repositories"
        print(f"[{Colors.CYAN}INF{Colors.RESET}] Starting scan of {Colors.BOLD}{len(all_targets)}{Colors.RESET} {target_type}")

    START_TIME = time.time()
    results = []

    for idx, target in enumerate(all_targets, 1):
        if INTERRUPTED:
            break

        if scan_type == "domain":
            result = scan_domain_target(target, idx, len(all_targets), scanner, args.registry)
        else:
            result = scan_repository(target, idx, len(all_targets), scanner, args.registry)

        if result:
            results.append(result)

    if results:
        for result in results:
            if result.get('vulnerable'):
                sorted_packages = sorted(result['vulnerable'].items(), key=lambda x: x[1], reverse=True)
                for pkg, confidence in sorted_packages:
                    if confidence >= 90:
                        conf_color = Colors.GREEN
                    elif confidence >= 70:
                        conf_color = Colors.YELLOW
                    else:
                        conf_color = Colors.RED
                    print(f"  {Colors.YELLOW}→{Colors.RESET} Unclaimed Package: {pkg}")

                    claim_url = {
                        'npm': f'https://www.npmjs.com/package/{pkg}',
                        'pypi': f'https://pypi.org/project/{pkg}/',
                        'rubygems': f'https://rubygems.org/gems/{pkg}'
                    }.get(result['registry'], f'https://www.npmjs.com/package/{pkg}')

                    print(f"    Claim URL: {claim_url}")
                    print(f"    Confidence: {conf_color}{confidence}%{Colors.RESET}")

            if result.get('vulnerable_wp'):
                for plugin in result['vulnerable_wp']:
                    print(f"  {Colors.YELLOW}→{Colors.RESET} Unclaimed WP Plugin: {plugin}")
                    print(f"    Claim URL: https://wordpress.org/plugins/{plugin}/")
                    print(f"    Confidence: {Colors.GREEN}90%{Colors.RESET}")

    elapsed_time = time.time() - START_TIME
    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Scan finished {Colors.DIM}({elapsed_time:.3f}s elapsed time){Colors.RESET}")
    cleanup()

if __name__ == '__main__':
    main()
