# SubEnum - Subdomain Enumeration Pipeline

A subdomain enumeration pipeline that automates reconnaissance using multiple tools.

## Features

-   **Passive enumeration** via subfinder, findomain, assetfinder, crt.sh, and chaos
-   **DNS bruteforcing** with shuffledns (optional)
-   **Port scanning** with dnsx + naabu (optional)
-   **Screenshots** using gowitness (optional)
-   Automatic result aggregation and deduplication

## Installation

Install the required tools:

```bash
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/chaos-client/cmd/chaos@latest
go install github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest
go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install github.com/sensepost/gowitness@latest
go install github.com/Findomain/Findomain@latest
go install github.com/tomnomnom/assetfinder@latest
go install github.com/cemulus/crtsh@latest
```

## Usage

Basic enumeration:

```bash
./subenum.py -d example.com -o output/
```

With DNS bruteforcing:

```bash
./subenum.py -d example.com -o output/ -sd -r resolvers.txt -w wordlist.txt
```

With port scanning and screenshots:

```bash
./subenum.py -d example.com -o output/ -r resolvers.txt -ps -s
```

### Options

```
-d   Target domain (required)
-o   Output directory (required)
-sd  Run shuffledns bruteforcing
-r   Resolvers file (required for -sd and -ps)
-w   Wordlist file (required for -sd)
-ps  Run port scanning
-s   Take screenshots
```

### Environment Variables

-   `CHAOS_API_KEY` - ProjectDiscovery Chaos API key (optional)
    ```bash
    export CHAOS_API_KEY="your-api-key-here"
    ```

## Output

Results are saved to the specified output directory:

-   `domains.txt` - Combined unique subdomains
-   `subfinder.txt`, `findomain.txt`, etc. - Individual tool results
-   `open-ports.txt` - Hosts with open ports (if -ps used)
-   `screenshots/` - Screenshots folder (if -s used)

## Responsible Disclosure

This tool is intended for authorized security testing and bug bounty programs only. Always ensure you have explicit permission before scanning any domain. Unauthorized scanning may be illegal in your jurisdiction.

-   Only test domains you own or have written authorization to test
-   Respect scope limitations in bug bounty programs
-   Follow responsible disclosure practices
-   Adhere to the target's security policy and terms of service

The authors assume no liability for misuse of this tool.
