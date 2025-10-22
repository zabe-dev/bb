#!/usr/bin/env python3

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
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
    print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Scan interrupted {Colors.DIM}({elapsed:.3f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def print_banner():
    print(rf"""{Colors.CYAN}
           _
 ___ _   _| |__   ___ _ __  _   _ _ __ ___
/ __| | | | '_ \ / _ \ '_ \| | | | '_ ` _ \
\__ \ |_| | |_) |  __/ | | | |_| | | | | | |
|___/\__,_|_.__/ \___|_| |_|\__,_|_| |_| |_|
{Colors.RESET}
{Colors.DIM}    Subdomain Enumeration Pipeline v{VERSION}{Colors.RESET}
""")

def check_tool(tool_name):
    try:
        subprocess.run([tool_name, "-h"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def run_command(cmd, output_file, spinner_msg, timeout=900):
    spinner = Spinner(spinner_msg)
    spinner.start()

    try:
        with open(output_file, 'w') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL,
                                  timeout=timeout, shell=isinstance(cmd, str))

        spinner.stop()

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                count = sum(1 for line in f if line.strip())

            if count > 0:
                print(f"[{Colors.GREEN}SUC{Colors.RESET}] {spinner_msg}: {count} found")
                return count
            else:
                print(f"[{Colors.RED}FAIL{Colors.RESET}] {spinner_msg}: 0 found")
                return 0
        else:
            spinner.stop()
            print(f"[{Colors.RED}FAIL{Colors.RESET}] {spinner_msg}: Failed")
            return 0

    except subprocess.TimeoutExpired:
        spinner.stop()
        print(f"[{Colors.ORANGE}WRN{Colors.RESET}] {spinner_msg}: Timeout (skipped)")
        return 0
    except Exception as e:
        spinner.stop()
        print(f"[{Colors.RED}ERR{Colors.RESET}] {spinner_msg}: {e}")
        return 0

def run_subfinder(domain, output_file):
    cmd = ["subfinder", "-silent", "-all", "-d", domain, "-o", output_file]
    return run_command(cmd, output_file, "Running subfinder...")

def run_findomain(domain, output_file):
    cmd = ["findomain", "-t", domain, "-q", "-r", "-u", output_file]
    return run_command(cmd, output_file, "Running findomain...")

def run_assetfinder(domain, output_file):
    cmd = f"assetfinder -subs-only {domain} > {output_file}"
    return run_command(cmd, output_file, "Running assetfinder...")

def run_crtsh(domain, output_file):
    cmd = ["crtsh", ">", domain]
    return run_command(cmd, output_file, "Running crtsh...")

def run_chaos(domain, output_file):
    api_key = os.environ.get('CHAOS_API_KEY')
    if not api_key:
        print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] Running chaos... CHAOS_API_KEY not set")
        return 0

    cmd = ["chaos", "-key", api_key, "-d", domain, "-silent", "-o", output_file]
    return run_command(cmd, output_file, "Running chaos...")

def run_shuffledns(domain, resolvers, wordlist, output_file):
    if not os.path.exists(resolvers):
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running shuffledns... Resolvers file not found")
        return 0

    if not os.path.exists(wordlist):
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running shuffledns... Wordlist file not found")
        return 0

    cmd = ["shuffledns", "-d", domain, "-r", resolvers, "-w", wordlist,
           "-mode", "bruteforce", "-silent"]
    return run_command(cmd, output_file, "Running shuffledns...", timeout=3600)

def run_port_scan(domains_file, resolvers, output_file):
    if not os.path.exists(resolvers):
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running dnsx + naabu... Resolvers file not found")
        return 0

    if not os.path.exists(domains_file):
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running dnsx + naabu... Domains file not found")
        return 0

    spinner = Spinner("Running dnsx + naabu...")
    spinner.start()

    try:
        cmd = f"cat {domains_file} | dnsx -silent -r {resolvers} -a -resp-only | naabu -silent -tp full > {output_file}"
        subprocess.run(cmd, shell=True, timeout=1800, stderr=subprocess.DEVNULL)

        spinner.stop()

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                count = sum(1 for line in f if line.strip())

            if count > 0:
                print(f"[{Colors.GREEN}SUC{Colors.RESET}] Running dnsx + naabu... {count} hosts with open ports")
                return count
            else:
                print(f"[{Colors.RED}FAIL{Colors.RESET}] Running dnsx + naabu... 0 open ports")
                return 0
        else:
            print(f"[{Colors.RED}FAIL{Colors.RESET}] Running dnsx + naabu... Failed")
            return 0

    except subprocess.TimeoutExpired:
        spinner.stop()
        print(f"[{Colors.ORANGE}WRN{Colors.RESET}] Running dnsx + naabu... Timeout")
        return 0
    except Exception as e:
        spinner.stop()
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running dnsx + naabu... {e}")
        return 0

def run_screenshots(domains_file, output_dir):
    if not os.path.exists(domains_file):
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running gowitness... Domains file not found")
        return 0

    spinner = Spinner("Running gowitness...")
    spinner.start()

    try:
        os.chdir(output_dir)
        cmd = ["gowitness", "scan", "file", "-f", domains_file, "--write-none"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7200)

        spinner.stop()
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Running gowitness... Screenshots saved")
        return 1

    except subprocess.TimeoutExpired:
        spinner.stop()
        print(f"[{Colors.ORANGE}WRN{Colors.RESET}] Running gowitness... Timeout")
        return 0
    except Exception as e:
        spinner.stop()
        print(f"[{Colors.RED}ERR{Colors.RESET}] Running gowitness... {e}")
        return 0

def combine_results(output_dir, domain):
    spinner = Spinner("Combining results...")
    spinner.start()

    all_domains = set()

    enum_files = [
        f"{output_dir}/subfinder.txt",
        f"{output_dir}/findomain.txt",
        f"{output_dir}/assetfinder.txt",
        f"{output_dir}/crtsh.txt",
        f"{output_dir}/chaos.txt",
        f"{output_dir}/shuffledns.txt"
    ]

    for file in enum_files:
        if os.path.exists(file):
            with open(file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_domains.add(line)

    domains_file = f"{output_dir}/domains.txt"
    with open(domains_file, 'w') as f:
        for d in sorted(all_domains):
            f.write(f"{d}\n")

    spinner.stop()

    count = len(all_domains)
    if count > 0:
        print(f"[{Colors.GREEN}SUC{Colors.RESET}] Combining results... {count} unique domains")
    else:
        print(f"[{Colors.RED}FAIL{Colors.RESET}] Combining results... 0 domains")

    return count

def verify_tools(args):
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Checking required tools...")

    required = ["subfinder", "findomain", "assetfinder", "crtsh"]
    optional = []

    if args.sd:
        required.append("shuffledns")

    if args.ps:
        required.extend(["dnsx", "naabu"])

    if args.s:
        optional.append("gowitness")

    if os.environ.get('CHAOS_API_KEY'):
        optional.append("chaos")

    missing = []
    for tool in required:
        if not check_tool(tool):
            missing.append(tool)
            print(f"[{Colors.RED}MISS{Colors.RESET}] {tool}")

    for tool in optional:
        if not check_tool(tool):
            print(f"[{Colors.ORANGE}SKIP{Colors.RESET}] {tool} (optional)")

    if missing:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Missing required tools: {', '.join(missing)}")
        sys.exit(1)

def main():
    global START_TIME

    parser = argparse.ArgumentParser(
        description="Subdomain enumeration pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-d", required=True, metavar="example.com", help="Target domain")
    parser.add_argument("-o", required=True, metavar="output/", help="Output directory")
    parser.add_argument("-sd", action="store_true", help="Run shuffledns bruteforcing")
    parser.add_argument("-r", metavar="resolvers.txt", help="List of resolvers for dns bruteforcing/port scanning")
    parser.add_argument("-w", metavar="wordlist.txt", help="List of subdomains for dns bruteforcing")
    parser.add_argument("-ps", action="store_true", help="Run port scanning")
    parser.add_argument("-s", action="store_true", help="Take screenshots")


    args = parser.parse_args()

    print_banner()
    START_TIME = time.time()

    if args.sd and (not args.r or not args.w):
        print(f"[{Colors.RED}ERR{Colors.RESET}] shuffledns requires -r and -w flags")
        sys.exit(1)

    if args.ps and not args.r:
        print(f"[{Colors.RED}ERR{Colors.RESET}] Port scan requires -r flag")
        sys.exit(1)

    verify_tools(args)

    output_dir = args.o
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"[{Colors.CYAN}INF{Colors.RESET}] Target: {args.d}")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Output: {output_dir}\n")

    results = {}

    results['subfinder'] = run_subfinder(args.d, f"{output_dir}/subfinder.txt")
    results['findomain'] = run_findomain(args.d, f"{output_dir}/findomain.txt")
    results['assetfinder'] = run_assetfinder(args.d, f"{output_dir}/assetfinder.txt")
    results['crtsh'] = run_crtsh(args.d, f"{output_dir}/crtsh.txt")
    results['chaos'] = run_chaos(args.d, f"{output_dir}/chaos.txt")

    if args.sd:
        results['shuffledns'] = run_shuffledns(
            args.d,
            args.r,
            args.w,
            f"{output_dir}/shuffledns.txt"
        )

    print()
    total = combine_results(output_dir, args.d)

    if args.ps and total > 0:
        print()
        results['portscan'] = run_port_scan(
            f"{output_dir}/domains.txt",
            args.r,
            f"{output_dir}/open-ports.txt"
        )

    if args.s and total > 0:
        print()
        results['screenshots'] = run_screenshots(f"{output_dir}/domains.txt", output_dir)

    elapsed = time.time() - START_TIME
    print(f"\n[{Colors.CYAN}INF{Colors.RESET}] Results saved to: {output_dir}/")
    print(f"[{Colors.CYAN}INF{Colors.RESET}] Time elapsed: {elapsed:.2f}s\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()
        print(f"\n[{Colors.ORANGE}WRN{Colors.RESET}] Interrupted by user")
        sys.exit(0)
