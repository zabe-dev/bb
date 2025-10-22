# URL Access Control Bypass Tester

A bash script for testing URL-based access control bypasses through various HTTP techniques.

## Usage

```bash
./bypass40X.sh https://example.com/path/to/resource
```

## What It Tests

### URL Manipulations

-   Path encoding variations (`%2e`, `%2f`, `%252f`)
-   Path traversal sequences (`..`, `../`, `..;`)
-   Trailing characters (`.`, `/`, `?`, `#`, `*`)
-   File extensions (`.html`, `.php`, `.json`, `.bak`, `.old`)
-   Unicode encodings (`%c0%ae`, `%e0%80%ae`)
-   Double/triple slashes (`//`, `///`)
-   Host-to-path injections (`https://example.com/../admin`)

### HTTP Headers

-   Method overrides (`X-HTTP-Method-Override`, `X-Method-Override`)
-   IP spoofing (`X-Forwarded-For`, `X-Real-IP`, `CF-Connecting-IP`)
-   URL rewrites (`X-Original-URL`, `X-Rewrite-URL`)
-   Authentication headers (`Authorization`, `Cookie`, `X-Admin`)
-   Proxy headers (`X-Forwarded-Host`, `Forwarded`)

### HTTP Methods

-   GET, POST, PUT, PATCH, HEAD, OPTIONS
-   TRACE, CONNECT, PROPFIND
-   Method override combinations

### Additional Checks

-   Case variations (UPPERCASE, lowercase)
-   Wayback Machine archive lookups

## Output

-   Lines with **200 responses** are highlighted in **green**
-   Format: `[STATUS_CODE] [SIZE] URL [OPTIONS]`

## Requirements

-   `curl`
-   `jq` (for Wayback Machine checks)
-   `bash` 4.0+

## Note

This tool is for authorized security testing only. Do not use against systems without permission.
