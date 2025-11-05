#!/usr/bin/env python3

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests


class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def normalize_url(url):
    if not url.startswith(('http://', 'https://')):
        return f'https://{url}'
    return url

def check_cors(url, origin='https://kspr.sh', timeout=10):
    result = {
        'url': url,
        'vulnerable': False,
        'allows_origin': None,
        'allows_credentials': False,
        'reflects_origin': False,
        'wildcard': False,
        'null_origin': False,
        'error': None
    }

    headers = {'Origin': origin}

    try:
        resp = requests.options(url, headers=headers, timeout=timeout, allow_redirects=True)

        if resp.status_code >= 400:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

        acao = resp.headers.get('Access-Control-Allow-Origin')
        acac = resp.headers.get('Access-Control-Allow-Credentials')

        if acao:
            result['allows_origin'] = acao
            result['allows_credentials'] = acac == 'true'

            if acao == '*':
                result['wildcard'] = True
                result['vulnerable'] = True
            elif acao == origin:
                result['reflects_origin'] = True
                result['vulnerable'] = True
            elif acao == 'null':
                result['null_origin'] = True
                result['vulnerable'] = True

            if result['wildcard'] and result['allows_credentials']:
                result['vulnerable'] = True

    except requests.exceptions.RequestException as e:
        result['error'] = str(e)

    if not result['error']:
        try:
            resp_null = requests.get(url, headers={'Origin': 'null'}, timeout=timeout)
            if resp_null.headers.get('Access-Control-Allow-Origin') == 'null':
                result['null_origin'] = True
                result['vulnerable'] = True
        except:
            pass

    return result

def print_result(result):
    url = result['url']

    if result['error']:
        print(f"[{Colors.YELLOW}error{Colors.RESET}] {url}\n")
        return

    if not result['allows_origin']:
        print(f"[{Colors.GREEN}secure{Colors.RESET}] {url}")
        print(f"  └─ No CORS headers found\n")
        return

    # Check if it's critical (credentials + vulnerable origin)
    is_critical = result['allows_credentials'] and (result['reflects_origin'] or result['null_origin'])

    if is_critical:
        status = f"[{Colors.RED}critical{Colors.RESET}]"
    elif result['vulnerable']:
        status = f"[{Colors.RED}vulnerable{Colors.RESET}]"
    else:
        status = f"[{Colors.CYAN}info{Colors.RESET}]"

    print(f"{status} {url}")
    print(f"  ├─ Access-Control-Allow-Origin: {result['allows_origin']}")
    print(f"  ├─ Access-Control-Allow-Credentials: {result['allows_credentials']}")

    issues = []
    if result['wildcard']:
        issues.append(f"  ├─ {Colors.RED}Wildcard (*) origin allowed{Colors.RESET}")
    if result['reflects_origin']:
        issues.append(f"  ├─ {Colors.RED}Reflects arbitrary origins{Colors.RESET}")
    if result['null_origin']:
        issues.append(f"  ├─ {Colors.RED}Reflects null origin{Colors.RESET}")

    if issues:
        for i, issue in enumerate(issues):
            if i == len(issues) - 1:
                print(issue.replace('├─', '└─'))
            else:
                print(issue)
    else:
        print(f"  └─")

    print()

def main():
    parser = argparse.ArgumentParser(description='Automated CORS misconfiguration detector')
    parser.add_argument('file', help='Text file with URLs/domains (one per line)')
    parser.add_argument('-o', default='https://kspr.sh',
                       help='Origin to test (default: https://kspr.sh)')
    parser.add_argument('-t', type=int, default=10,
                       help='Number of concurrent threads (default: 10)')
    parser.add_argument('-m', type=int, default=10,
                       help='Request timeout in seconds (default: 10)')
    parser.add_argument('-w', help='Save results to file')

    args = parser.parse_args()

    try:
        with open(args.file, 'r') as f:
            urls = [normalize_url(line.strip()) for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print(f"Error: File '{args.file}' not found")
        return

    if not urls:
        print("No URLs found in file")
        return

    results = []
    vulnerable_count = 0
    error_count = 0

    print()

    with ThreadPoolExecutor(max_workers=args.t) as executor:
        future_to_url = {
            executor.submit(check_cors, url, args.o, args.m): url
            for url in urls
        }

        print(f"{Colors.BOLD}URLs:{Colors.RESET} {len(urls)} | {Colors.BOLD}Origin:{Colors.RESET} {args.o} | {Colors.BOLD}Threads:{Colors.RESET} {args.t}\n")

        for future in as_completed(future_to_url):
            result = future.result()
            results.append(result)
            print_result(result)

            if result['vulnerable']:
                vulnerable_count += 1
            if result['error']:
                error_count += 1

    if args.w:
        with open(args.w, 'w') as f:
            for r in results:
                if r['vulnerable']:
                    f.write(f"{r['url']}\n")
        print(f"\nVulnerable URLs saved to: {args.w}")

if __name__ == '__main__':
    main()
