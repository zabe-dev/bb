# staticdl

A fast, intelligent static file downloader that handles duplicates, redirects, and parallel downloads.

## Features

-   **Smart duplicate detection** using SHA-256 hashing
-   **Parallel downloads** with aria2c (16 connections) or curl fallback
-   **Redirect tracking** to avoid downloading the same file twice
-   **Size limits** to skip oversized files
-   **Automatic file renaming** to prevent overwrites
-   **Resume capability** by detecting existing files

## Installation

```bash
chmod +x staticdl
sudo mv staticdl /usr/local/bin/
```

## Usage

```bash
staticdl -f urls.txt -o output/
```

### Options

-   `-f <file>` - File containing URLs (one per line)
-   `-o <dir>` - Output directory for downloaded files
-   `-max <bytes>` - Maximum file size (default: 10MB)
-   `-h` - Show help message

### Examples

```bash
staticdl -f urls.txt -o downloads/
staticdl -f assets.txt -o public/ -max 5242880
staticdl -f images.txt -o img/ -max $((20 * 1024 * 1024))
```

## Requirements

-   **Required**: `curl` or `aria2c`, `file`, `sha256sum` (or `shasum`)
-   **Recommended**: `aria2c` for faster downloads

## URL File Format

Create a text file with one URL per line:

```
https://example.com/image1.jpg
https://example.com/script.js
https://cdn.example.com/style.css
```

Lines starting with `#` are ignored as comments.

## License

MIT
