#!/usr/bin/env python3

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import threading
import time
from typing import Dict, List, Optional

import requests
import yaml

VERSION = "1.0.0"
START_TIME = None
INTERRUPTED = False

class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    ORANGE = '\033[93m'
    RED = '\033[91m'
    PURPLE = '\033[95m'
    BLUE = '\033[94m'
    PINK = '\033[38;5;213m'
    YELLOW = '\033[93m'
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
                    sys.stdout.write(f'\r\033[K{Colors.CYAN}{self.spinner[idx % len(self.spinner)]}{Colors.RESET} {self.message}')
                    sys.stdout.flush()
            idx += 1
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
    current_time = time.strftime('%H:%M:%S')
    print(f"\n\n{Colors.DIM}[{current_time}]{Colors.RESET} {Colors.ORANGE}[WRN]{Colors.RESET} Scan interrupted {Colors.DIM}({elapsed:.1f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def print_banner():
    print(rf"""{Colors.CYAN}

  _ __ ___ _ __   ___  ___  ___ __ _ _ __
 | '__/ _ \ '_ \ / _ \/ __|/ __/ _` | '_ \
 | | |  __/ |_) | (_) \__ \ (_| (_| | | | |
 |_|  \___| .__/ \___/|___/\___\__,_|_| |_|
          |_|
{Colors.RESET}
{Colors.DIM}    GitHub Security Scanner v{VERSION}{Colors.RESET}
""")

class SecurityDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def init_db(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS repositories (id INTEGER PRIMARY KEY, full_name TEXT UNIQUE, org TEXT, name TEXT, private INTEGER, fork_count INTEGER, last_scanned INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS forks (id INTEGER PRIMARY KEY, parent_repo TEXT, owner TEXT, name TEXT, created_at TEXT, updated_at TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS vulnerabilities (id INTEGER PRIMARY KEY AUTOINCREMENT, repo_full_name TEXT, type TEXT, severity TEXT, details TEXT, timestamp INTEGER)")
        self.conn.commit()

    def save_repository(self, repo: Dict):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO repositories (id, full_name, org, name, private, fork_count, last_scanned) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (repo['id'], repo['full_name'], repo['org'], repo['name'], 1 if repo['private'] else 0, repo['fork_count'], repo['last_scanned']))
        self.conn.commit()

    def get_repository(self, full_name: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE full_name = ?", (full_name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_fork(self, fork: Dict):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO forks (id, parent_repo, owner, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (fork['id'], fork['parent_repo'], fork['owner'], fork['name'], fork['created_at'], fork['updated_at']))
        self.conn.commit()

    def get_forks_by_parent(self, parent: str) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM forks WHERE parent_repo = ?", (parent,))
        return [dict(row) for row in cursor.fetchall()]

    def save_vulnerability(self, vuln: Dict):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO vulnerabilities (repo_full_name, type, severity, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                       (vuln['repo_full_name'], vuln['type'], vuln['severity'], vuln['details'], vuln['timestamp']))
        self.conn.commit()

    def has_vulnerability(self, repo_full_name: str, vuln_type: str, details: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vulnerabilities WHERE repo_full_name = ? AND type = ? AND details = ?", (repo_full_name, vuln_type, details))
        return cursor.fetchone()[0] > 0

    def get_vulnerabilities(self, repo_full_name: str) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM vulnerabilities WHERE repo_full_name = ?", (repo_full_name,))
        return [dict(row) for row in cursor.fetchall()]

    def purge(self):
        cursor = self.conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS repositories")
        cursor.execute("DROP TABLE IF EXISTS forks")
        cursor.execute("DROP TABLE IF EXISTS vulnerabilities")
        self.conn.commit()
        self.init_db()

    def close(self):
        if self.conn:
            self.conn.close()

class GitHubClient:
    def __init__(self, tokens: List[str]):
        self.tokens = [t for t in tokens if t]
        self.idx = 0

    @property
    def token(self) -> Optional[str]:
        return self.tokens[self.idx % len(self.tokens)] if self.tokens else None

    def rotate(self):
        self.idx += 1

    def request(self, url: str) -> Dict:
        if not self.token:
            raise Exception("No token")
        headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3+json'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 403 and response.headers.get('X-RateLimit-Remaining') == '0':
            self.rotate()
            raise Exception("Rate limit")
        if not response.ok:
            raise Exception(f"API error: {response.status_code}")
        return response.json()

    def raw(self, url: str) -> str:
        if not self.token:
            raise Exception("No token")
        headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3.raw'}
        response = requests.get(url, headers=headers, timeout=10)
        if not response.ok:
            raise Exception(f"API error: {response.status_code}")
        return response.text

    def get_org_repos(self, org: str, page: int = 1) -> List[Dict]:
        return self.request(f'https://api.github.com/orgs/{org}/repos?page={page}&per_page=100&type=all')

    def get_repo_forks(self, owner: str, repo: str, page: int = 1) -> List[Dict]:
        return self.request(f'https://api.github.com/repos/{owner}/{repo}/forks?page={page}&per_page=100')

    def get_file(self, owner: str, repo: str, path: str) -> str:
        return self.raw(f'https://api.github.com/repos/{owner}/{repo}/contents/{path}')

    def get_repo_contents(self, owner: str, repo: str, path: str = "") -> List[Dict]:
        return self.request(f'https://api.github.com/repos/{owner}/{repo}/contents/{path}')

    def get_commits(self, owner: str, repo: str, page: int = 1) -> List[Dict]:
        return self.request(f'https://api.github.com/repos/{owner}/{repo}/commits?page={page}&per_page=100')

    def check_user(self, username: str) -> bool:
        try:
            self.request(f'https://api.github.com/users/{username}')
            return True
        except:
            return False

def log(msg_type: str, message: str, repo: str = None, spinner: Optional[Spinner] = None):
    icons = {
        'info': ('INF', Colors.BLUE),
        'success': ('INF', Colors.GREEN),
        'warning': ('WRN', Colors.ORANGE),
        'error': ('ERR', Colors.RED),
        'fork': ('new-forks', Colors.PURPLE),
        'dependency': ('dependency-confusion', Colors.ORANGE),
        'link': ('broken-link', Colors.YELLOW),
        'takeover': ('username-takeover', Colors.RED),
        'sensitive': ('sensitive-file', Colors.PINK),
        'scan': ('INF', Colors.CYAN)
    }

    label, color = icons.get(msg_type, ('INF', Colors.CYAN))

    if spinner:
        spinner.pause()

    timestamp = time.strftime('%H:%M:%S')

    if repo:
        print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} [{color}{label}{Colors.RESET}] [{repo}] {message}")
    else:
        print(f"{Colors.DIM}[{timestamp}]{Colors.RESET} [{color}{label}{Colors.RESET}] {message}")

    if spinner:
        spinner.resume()

def check_npm_package(name: str) -> bool:
    try:
        r = requests.get(f'https://registry.npmjs.org/{name}', timeout=5)
        return r.ok
    except:
        return False

def check_url(url: str) -> bool:
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.ok
    except:
        return False

def extract_urls(text: str) -> List[str]:
    return list(set(re.findall(r'https?://[^\s\)\]\}]+', text)))

def extract_usernames(text: str) -> List[str]:
    return list(set(re.findall(r'@([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?)', text)))

def send_discord_webhook(webhook_url: str, vuln_type: str, org: str, repo: str, details: str, severity: str, file_path: str = None, extra_info: Dict = None):
    if not webhook_url:
        return

    colors = {'critical': 15158332, 'high': 15105570, 'medium': 16776960, 'low': 3447003}

    severity_emoji = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'low': '🔵'
    }

    full_name = f"{org}/{repo}"
    repo_url = f"https://github.com/{full_name}"

    fields = [
        {'name': '📦 Repository', 'value': f"[{full_name}]({repo_url})", 'inline': True},
        {'name': '⚠️ Severity', 'value': f"{severity_emoji.get(severity, '⚪')} {severity.upper()}", 'inline': True},
        {'name': '🕐 Detected', 'value': f"<t:{int(time.time())}:R>", 'inline': True}
    ]

    if file_path:
        file_url = f"{repo_url}/blob/main/{file_path}"
        fields.append({'name': '📄 File', 'value': f"[{file_path}]({file_url})", 'inline': False})

    if extra_info:
        for key, value in extra_info.items():
            fields.append({'name': key, 'value': value, 'inline': False})

    fields.append({'name': '🔍 Details', 'value': f"```{details}```", 'inline': False})

    embed = {
        'title': f"🚨 {vuln_type}",
        'description': f"Security issue detected in **{full_name}**",
        'color': colors.get(severity, colors['medium']),
        'fields': fields,
        'footer': {'text': f"reposcan v{VERSION}"},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    }

    try:
        requests.post(webhook_url, json={'embeds': [embed]}, timeout=10)
    except:
        pass

def scan_forks(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    if not config.get('enable_fork_tracking', True):
        return
    full_name = f"{org}/{repo['name']}"
    forks = []
    page = 1
    while not INTERRUPTED:
        try:
            data = client.get_repo_forks(org, repo['name'], page)
            if not data:
                break
            forks.extend(data)
            page += 1
        except:
            break
    stored = db.get_repository(full_name)
    old_forks = db.get_forks_by_parent(full_name) if stored else []
    is_first = not stored
    db.save_repository({'id': repo['id'], 'full_name': full_name, 'org': org, 'name': repo['name'], 'private': repo.get('private', False), 'fork_count': len(forks), 'last_scanned': int(time.time())})
    if not is_first:
        new = [f for f in forks if not any(o['id'] == f['id'] for o in old_forks)]
        if new:
            fork_list = [f"{f['owner']['login']}/{f['name']}" for f in new[:3]]
            fork_display = ', '.join(fork_list)
            if len(new) > 3:
                fork_display += f" +{len(new)-3} more"
            log('fork', f"{len(new)} new fork(s): {fork_display}", full_name, spinner)
            db.save_vulnerability({'repo_full_name': full_name, 'type': 'new_forks', 'severity': 'medium', 'details': f"{len(new)} new forks detected", 'timestamp': int(time.time())})
            if config.get('enable_discord'):
                extra_info = {'🌿 New Forks': ', '.join([f"`{f['owner']['login']}/{f['name']}`" for f in new[:5]])}
                if len(new) > 5:
                    extra_info['🌿 New Forks'] += f"\n... and {len(new)-5} more"
                send_discord_webhook(config['discord_webhook'], 'New Forks Detected', org, repo['name'], f"{len(new)} new fork(s) detected", 'medium', extra_info=extra_info)
            stats['fork_changes'] += 1
            stats['total_issues'] += 1
    if stored and stored['private'] and not repo.get('private', False):
        log('fork', f"visibility changed: PRIVATE → PUBLIC", full_name, spinner)
        db.save_vulnerability({'repo_full_name': full_name, 'type': 'visibility', 'severity': 'critical', 'details': 'Repository changed from private to public', 'timestamp': int(time.time())})
        if config.get('enable_discord'):
            send_discord_webhook(config['discord_webhook'], 'Repository Visibility Change', org, repo['name'], 'Repository is now PUBLIC (was private)', 'critical', extra_info={'⚠️ Warning': 'Private repository is now publicly accessible'})
        stats['fork_changes'] += 1
        stats['total_issues'] += 1
    for f in forks:
        db.save_fork({'id': f['id'], 'parent_repo': full_name, 'owner': f['owner']['login'], 'name': f['name'], 'created_at': f['created_at'], 'updated_at': f['updated_at']})

def scan_dependencies(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    if not config.get('enable_dependency_check', True):
        return
    full_name = f"{org}/{repo['name']}"
    try:
        pkg = json.loads(client.get_file(org, repo['name'], 'package.json'))
    except:
        return
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    if not deps:
        return
    for name, ver in deps.items():
        if INTERRUPTED:
            break
        stats['npm_packages'] += 1
        if not check_npm_package(name):
            details = f"{name}@{ver}"
            if not config.get('alert_only_new_issues', True) or not db.has_vulnerability(full_name, 'dependency_confusion', details):
                log('dependency', f"{name}@{ver}", full_name, spinner)
                db.save_vulnerability({'repo_full_name': full_name, 'type': 'dependency_confusion', 'severity': 'high', 'details': details, 'timestamp': int(time.time())})
                if config.get('enable_discord'):
                    send_discord_webhook(config['discord_webhook'], 'Dependency Confusion Risk', org, repo['name'], f"Package {name}@{ver} not found in npm registry", 'high', 'package.json', extra_info={'📦 Package': f"`{name}@{ver}`", '⚠️ Risk': 'Potential dependency confusion attack vector'})
                stats['dependencies'] += 1
                stats['total_issues'] += 1

def scan_links(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    if not config.get('enable_link_check', True):
        return
    full_name = f"{org}/{repo['name']}"
    for fname in ['README.md', 'README']:
        try:
            text = client.get_file(org, repo['name'], fname)
            urls = extract_urls(text)[:10]
            for url in urls:
                if INTERRUPTED:
                    break
                stats['links_checked'] += 1
                if not check_url(url):
                    details = f"{fname}: {url}"
                    if not config.get('alert_only_new_issues', True) or not db.has_vulnerability(full_name, 'broken_link', details):
                        log('link', f"{url}", full_name, spinner)
                        db.save_vulnerability({'repo_full_name': full_name, 'type': 'broken_link', 'severity': 'low', 'details': details, 'timestamp': int(time.time())})
                        if config.get('enable_discord'):
                            send_discord_webhook(config['discord_webhook'], 'Broken Link Detected', org, repo['name'], url, 'low', fname, extra_info={'🔗 URL': f"`{url}`", '📄 Location': f"`{fname}`"})
                        stats['broken_links'] += 1
                        stats['total_issues'] += 1
            break
        except:
            continue

def scan_takeover(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    if not config.get('enable_takeover_scan', True):
        return
    full_name = f"{org}/{repo['name']}"
    users = set()
    for p in range(1, 4):
        if INTERRUPTED:
            break
        try:
            for c in client.get_commits(org, repo['name'], p):
                if c.get('author', {}).get('login'):
                    users.add(c['author']['login'])
                if c.get('committer', {}).get('login'):
                    users.add(c['committer']['login'])
        except:
            break
    try:
        users.update(extract_usernames(client.get_file(org, repo['name'], 'README.md')))
    except:
        pass
    for u in list(users)[:20]:
        if INTERRUPTED:
            break
        stats['users_checked'] += 1
        if not client.check_user(u):
            details = f"@{u}"
            if not config.get('alert_only_new_issues', True) or not db.has_vulnerability(full_name, 'username_takeover', details):
                log('takeover', f"@{u}", full_name, spinner)
                db.save_vulnerability({'repo_full_name': full_name, 'type': 'username_takeover', 'severity': 'high', 'details': details, 'timestamp': int(time.time())})
                if config.get('enable_discord'):
                    send_discord_webhook(config['discord_webhook'], 'Username Takeover Risk', org, repo['name'], f"Username @{u} is available for registration", 'high', extra_info={'👤 Username': f"`@{u}`", '⚠️ Risk': 'Attacker could register this username and impersonate contributor'})
                stats['takeovers'] += 1
                stats['total_issues'] += 1

def scan_sensitive_files(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    if not config.get('enable_sensitive_files', True):
        return
    full_name = f"{org}/{repo['name']}"
    patterns = ['.env', '.pem', '.p12', '.npmrc', 'id_rsa', '.key', 'password', 'token']
    exclude = ['test', 'demo', 'example']
    def walk(items, path="", depth=0):
        if depth > 3 or INTERRUPTED:
            return
        for i in items:
            if INTERRUPTED:
                return
            ip = f"{path}/{i['name']}" if path else i['name']
            if any(e in ip.lower() for e in exclude):
                continue
            if i['type'] == 'file':
                for p in patterns:
                    if p in i['name'].lower():
                        details = f"{ip} ({p})"
                        if not config.get('alert_only_new_issues', True) or not db.has_vulnerability(full_name, 'sensitive_file', details):
                            log('sensitive', f"{ip}", full_name, spinner)
                            db.save_vulnerability({'repo_full_name': full_name, 'type': 'sensitive_file', 'severity': 'critical', 'details': details, 'timestamp': int(time.time())})
                            if config.get('enable_discord'):
                                send_discord_webhook(config['discord_webhook'], 'Sensitive File Exposed', org, repo['name'], f"Potentially sensitive file found: {ip}", 'critical', ip, extra_info={'🔑 Pattern': f"`{p}`", '⚠️ Risk': 'May contain credentials or private keys'})
                            stats['sensitive_files'] += 1
                            stats['total_issues'] += 1
                        break
            elif i['type'] == 'dir' and depth < 3:
                try:
                    walk(client.get_repo_contents(org, repo['name'], ip), ip, depth+1)
                except:
                    pass
    try:
        walk(client.get_repo_contents(org, repo['name'], ''))
    except:
        pass

def scan_repository(client: GitHubClient, db: SecurityDB, org: str, repo: Dict, config: Dict, stats: Dict, spinner: Optional[Spinner]):
    full_name = f"{org}/{repo['name']}"
    try:
        scan_forks(client, db, org, repo, config, stats, spinner)
        scan_dependencies(client, db, org, repo, config, stats, spinner)
        scan_links(client, db, org, repo, config, stats, spinner)
        scan_takeover(client, db, org, repo, config, stats, spinner)
        scan_sensitive_files(client, db, org, repo, config, stats, spinner)
        stats['total'] += 1
    except Exception as e:
        log('error', f"scan failed → {str(e)}", full_name, spinner)

def fetch_org_repositories(client: GitHubClient, org: str, spinner: Optional[Spinner]) -> List[Dict]:
    repos = []
    page = 1
    while not INTERRUPTED:
        try:
            data = client.get_org_repos(org, page)
            if not data:
                break
            active = [r for r in data if not r.get('archived', False)]
            repos.extend(active)
            page += 1
        except:
            break
    return repos

def print_stats(stats: Dict):
    width = 50

    repos_scanned_spacing = width - 22 - len(str(stats['total']))
    fork_changes_spacing = width - 14 - len(str(stats['fork_changes']))
    dependency_spacing = width - 19 - len(str(stats['dependencies']))
    broken_links_spacing = width - 14 - len(str(stats['broken_links']))
    takeovers_spacing = width - 20 - len(str(stats['takeovers']))
    sensitive_spacing = width - 17 - len(str(stats['sensitive_files']))
    total_spacing = width - 20 - len(str(stats['total_issues']))

    print(rf"""
{Colors.CYAN}╭{'─' * width}╮{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.BOLD}Scan Results{Colors.RESET}{' ' * (width - 13)}{Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}├{'─' * width}┤{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} Repositories Scanned{' ' * repos_scanned_spacing}{Colors.BOLD}{stats['total']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}├{'─' * width}┤{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.PURPLE}Fork Changes{Colors.RESET}{' ' * fork_changes_spacing}{Colors.PURPLE}{stats['fork_changes']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.ORANGE}Dependency Issues{Colors.RESET}{' ' * dependency_spacing}{Colors.ORANGE}{stats['dependencies']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.YELLOW}Broken Links{Colors.RESET}{' ' * broken_links_spacing}{Colors.YELLOW}{stats['broken_links']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.RED}Username Takeovers{Colors.RESET}{' ' * takeovers_spacing}{Colors.RED}{stats['takeovers']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.PINK}Sensitive Files{Colors.RESET}{' ' * sensitive_spacing}{Colors.PINK}{stats['sensitive_files']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}├{'─' * width}┤{Colors.RESET}
{Colors.CYAN}│{Colors.RESET} {Colors.RED}{Colors.BOLD}Total Issues Found{Colors.RESET}{' ' * total_spacing}{Colors.RED}{Colors.BOLD}{stats['total_issues']}{Colors.RESET} {Colors.CYAN}│{Colors.RESET}
{Colors.CYAN}╰{'─' * width}╯{Colors.RESET}
""")

def save_json_output(file: str, results: Dict, elapsed: float):
    data = {'scan_time': elapsed, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'), 'statistics': results['stats'], 'organizations': results['organizations']}
    try:
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
        log('success', f"Results saved to {Colors.BOLD}{file}{Colors.RESET}")
    except Exception as e:
        log('error', f"Failed to save results → {e}")

def load_config(path: str) -> Dict:
    if not os.path.exists(path):
        log('error', f"Configuration file not found: {path}")
        sys.exit(1)
    try:
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
        if not cfg.get('github_tokens'):
            log('error', "Missing 'github_tokens' in configuration file")
            sys.exit(1)
        if 'database' not in cfg:
            log('error', "Missing 'database' in configuration file")
            sys.exit(1)
        return cfg
    except Exception as e:
        log('error', f"Configuration error → {e}")
        sys.exit(1)

def read_orgs_file(path: str) -> List[str]:
    try:
        with open(path) as f:
            return [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        log('error', f"Organizations file not found: {path}")
        sys.exit(1)

def main():
    global START_TIME
    parser = argparse.ArgumentParser(
        description="GitHub Security Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False
    )
    parser.add_argument('-h', '--help', action='help', help='show this help message and exit')
    parser.add_argument('-o', metavar='example', help='Organization to scan')
    parser.add_argument('-oL', metavar='organizations.txt', help='File with list of organizations')
    parser.add_argument('-c', metavar='config.yml', default='config.yml', help='Config file (YAML)')
    parser.add_argument('-output', metavar='results.json', help='Save results to JSON')
    parser.add_argument('--purge', action='store_true', help='Purge DB and exit')
    args = parser.parse_args()

    config = load_config(args.c)

    if args.purge:
        db = SecurityDB(config['database'])
        db.purge()
        log('success', f"Database purged: {Colors.BOLD}{config['database']}{Colors.RESET}")
        db.close()
        sys.exit(0)

    if not args.o and not args.oL:
        log('error', "Please specify either -o <organization> or -oL <file>")
        sys.exit(1)
    if args.o and args.oL:
        log('error', "Cannot use both -o and -oL flags")
        sys.exit(1)

    orgs = read_orgs_file(args.oL) if args.oL else [args.o]
    print_banner()

    log('info', f"Loaded {Colors.BOLD}{len(config['github_tokens'])}{Colors.RESET} GitHub token(s)")
    log('info', f"Database: {Colors.BOLD}{config['database']}{Colors.RESET}")
    log('info', f"Scanning {Colors.BOLD}{len(orgs)}{Colors.RESET} organization(s)\n")

    START_TIME = time.time()
    db = SecurityDB(config['database'])
    client = GitHubClient(config['github_tokens'])
    stats = {'total':0,'fork_changes':0,'dependencies':0,'broken_links':0,'takeovers':0,'sensitive_files':0,'users_checked':0,'links_checked':0,'npm_packages':0,'total_issues':0}
    results = {'stats': stats, 'organizations': {}}

    for idx, org in enumerate(orgs, 1):
        if INTERRUPTED:
            break
        current_time = time.strftime('%H:%M:%S')
        print(f"{Colors.DIM}[{current_time}]{Colors.RESET} {Colors.CYAN}[{idx}/{len(orgs)}]{Colors.RESET} Scanning: {Colors.BOLD}https://github.com/{org}{Colors.RESET}")
        spinner = Spinner(f"Fetching repositories from {org}")
        spinner.start()
        repos = fetch_org_repositories(client, org, spinner)
        spinner.stop()
        if not repos:
            log('warning', f"No repositories found for {Colors.BOLD}{org}{Colors.RESET}")
            continue
        log('info', f"Found {Colors.BOLD}{len(repos)}{Colors.RESET} active repository")
        results['organizations'][org] = []
        for r_idx, repo in enumerate(repos, 1):
            if INTERRUPTED:
                break
            spinner = Spinner(f"[{r_idx}/{len(repos)}] Scanning {org}/{repo['name']}")
            spinner.start()
            scan_repository(client, db, org, repo, config, stats, spinner)
            spinner.stop()
            full = f"{org}/{repo['name']}"
            vulns = len(db.get_vulnerabilities(full))
            results['organizations'][org].append({'repository': repo['name'], 'vulnerabilities': vulns})
        print()

    elapsed = time.time() - START_TIME
    print_stats(stats)
    if args.output:
        save_json_output(args.output, results, elapsed)
    log('info', f"Scan completed {Colors.DIM}({elapsed:.1f}s time elapsed){Colors.RESET}")
    db.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}[ERR]{Colors.RESET} {e}")
        sys.exit(1)
