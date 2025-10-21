# DepConf - Dependency Confusion Scanner

Automated security tool that scans domains, GitHub repositories, and organizations for unclaimed dependencies vulnerable to supply chain attacks.

## Features

-   Scans GitHub organizations, users, and individual repositories
-   Analyzes web domains for JavaScript dependencies and WordPress plugins
-   Detects unclaimed packages across npm, PyPI, and RubyGems registries
-   Concurrent scanning with configurable thread count
-   Confidence scoring for detected vulnerabilities

## Requirements

```bash
pip install requests
```

**GitHub Token (Optional but Recommended):**

```bash
export GITHUB_TOKEN="GITHUB_ACCESS_TOKEN"
```

**Note:** This tool requires and uses [TruffleHog](https://github.com/trufflesecurity/trufflehog) under the hood for secret detection such as API keys, tokens, secrets and passwords.

## Usage

```bash
python depconf.py -h
```

## Output Example

```
[001/150] [origin] [archived] example-org/legacy-app [2 vulnerable]
  → Unclaimed Package: @company/internal-utils
    Claim URL: https://www.npmjs.com/package/@company/internal-utils
    Confidence: 95%
  → Unclaimed WP Plugin: custom-contact-form
    Claim URL: https://wordpress.org/plugins/custom-contact-form/
    Confidence: 90%
```

## Supported Registries

-   npm (Node.js packages)
-   PyPI (Python packages)
-   RubyGems (Ruby gems)
-   WordPress.org (WordPress plugins)

## Responsible Disclosure

This tool identifies **potential** dependency confusion vulnerabilities for authorized security assessments only. Always:

-   Obtain explicit permission before scanning targets you don't own
-   Use findings for defensive purposes (securing your own infrastructure)
-   Report vulnerabilities through appropriate channels
-   Do NOT register packages to exploit discovered vulnerabilities

**Legal Warning:** Registering packages with names used by private dependencies without authorization may violate computer fraud laws and terms of service.
