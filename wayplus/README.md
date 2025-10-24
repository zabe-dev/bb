# wayplus

Automated web archive analysis tool for security reconnaissance. Fetches historical URLs, crawls live sites, and performs comprehensive vulnerability pattern detection.

## Features

-   Fetches archived URLs from Wayback Machine and other sources
-   Crawls live sites for active endpoints
-   Extracts subdomains, parameters, and API endpoints
-   Identifies sensitive URLs (tokens, keys, sessions, passwords)
-   Analyzes and decodes JWT tokens from URLs
-   Detects vulnerability patterns (XSS, SQLi, LFI, RCE, SSRF, SSTI, redirects, IDOR)
-   Finds compressed files, backups, and directory listings
-   Discovers JSON and config files
-   Automatically categorizes and saves all findings

## Requirements

```bash
pip install requests jwt waymore
```

**External Dependencies:**

-   [waymore](https://github.com/xnl-h4ck3r/waymore) - Archive URL fetching
-   [katana](https://github.com/projectdiscovery/katana) - Live site crawling
-   [gf](https://github.com/tomnomnom/gf) - Pattern matching for vulnerability detection
-   [Gf-Patterns](https://github.com/1ndianl33t/Gf-Patterns) - Pre-built pattern files for gf

**Install external tools:**

```bash
go install github.com/tomnomnom/gf@latest
git clone https://github.com/1ndianl33t/Gf-Patterns ~/.gf
CGO_ENABLED=1 go install github.com/projectdiscovery/katana/cmd/katana@latest
```

## Usage

```bash
python wayplus.py -d example.com -output results/
```

**Arguments:**

-   `-d` - Target domain (e.g., example.com)
-   `-output` - Output directory for results

## Output Structure

```
results/
├── example.com_urls.txt          # All archived URLs
├── example.com_katana.txt        # Crawled URLs
├── example.com_combined.txt      # Combined unique URLs
├── example.com_subdomains.txt    # Discovered subdomains
├── example.com_apis.txt          # API endpoints
├── example.com_secrets.txt       # URLs with sensitive parameters
├── example.com_parameters.txt    # Unique parameter combinations
├── example.com_jwt.json          # Decoded JWT tokens
├── example.com_static.txt        # Static files (js, css, images)
├── example.com_compressed.txt    # Archives and backups
├── example.com_json.txt          # JSON endpoints
├── example.com_config.txt        # Config files
├── example.com_dir_listings.txt  # Directory listings
├── example.com_xss.txt           # XSS patterns
├── example.com_sqli.txt          # SQL injection patterns
├── example.com_lfi.txt           # Local file inclusion
├── example.com_rce.txt           # Remote code execution
├── example.com_redirect.txt      # Open redirects
├── example.com_ssrf.txt          # Server-side request forgery
├── example.com_ssti.txt          # Server-side template injection
└── example.com_idor.txt          # Insecure direct object references
```

## Responsible Use

This tool is for **authorized security testing only**. Always obtain proper authorization before testing systems you don't own. Use responsibly and follow ethical disclosure practices.

## License

For educational and authorized security testing purposes.
