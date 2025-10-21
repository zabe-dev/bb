# Wayback URL Analyzer

Automated reconnaissance tool that fetches archived URLs using Waymore and performs comprehensive security analysis.

## Features

-   Fetches historical URLs from web archives via Waymore
-   Extracts subdomains and API endpoints
-   Identifies sensitive parameters and JWT tokens
-   Scans for XSS, SQLi, LFI, and open redirect patterns
-   Finds backup files and directory listings
-   Categorizes and saves results automatically

## Requirements

```bash
pip install requests PyJWT waymore
```

**Note:** This tool uses [Waymore](https://github.com/xnl-h4ck3r/waymore) behind the scenes to fetch archived URLs from multiple sources including Wayback Machine, Common Crawl, and VirusTotal.

## Usage

```bash
python wayplus.py
```

Enter target domain and output directory. Analysis runs automatically and saves categorized results.

## Output Structure

```
output_dir/
├── target_urls.txt
├── target_subdomains.txt
├── target_apis.txt
├── target_sensitive.txt
├── target_parameters.txt
├── target_jwt.json
├── target_xss.txt
├── target_sqli.txt
└── ...
```

## Pattern Databases

Place pattern files in `db/` directory:

-   xss.txt
-   sqli.txt
-   lfi.txt
-   openredirect.txt
-   jira.txt
-   wp-fuzz.txt
-   fuzz.txt

## Responsible Disclosure

This tool is intended for security research and authorized testing only. Always obtain proper authorization before testing any systems you do not own. Respect responsible disclosure practices and report vulnerabilities through appropriate channels.
