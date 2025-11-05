#!/usr/bin/env bash

# Usage:
# chmod +x file-upload-exfil-scanner.sh
# ./file-upload-exfil-scanner.sh original.jpg downloaded.jpg

orig="$1"; down="$2"
if [ -z "$orig" ] || [ -z "$down" ]; then
  echo "Usage: $0 original-file downloaded-file"; exit 1
fi

echo "=== HASHES ==="
sha256sum "$orig" "$down" 2>/dev/null || shasum -a 256 "$orig" "$down"
echo

echo "=== SIZES ==="
# macOS-compatible stat (BSD)
if stat -f "%z" "$orig" >/dev/null 2>&1; then
  echo "$orig: $(stat -f "%z" "$orig") bytes"
  echo "$down: $(stat -f "%z" "$down") bytes"
else
  # fallback for Linux/GNU
  stat --printf="%n: %s bytes\n" "$orig" "$down"
fi
echo

echo "=== CMP QUICK ==="
if cmp -s "$orig" "$down"; then
  echo "IDENTICAL (cmp -s)"
else
  echo "DIFFER (cmp -s)"
  echo "First differing bytes (cmp -l):"
  cmp -l "$orig" "$down" | head -n 20
fi
echo

echo "=== STRINGS (suspicious keywords) ==="
strings "$down" | egrep -i 'aws|akia|secret|token|password|session|key|bearer|auth|eyj|api' | head -n 60 || echo "(no obvious strings)"
echo

echo "=== HEXITAIL CHECKS (common EOF markers) ==="
file_type=$(file --brief --mime-type "$down")

case "$file_type" in
  image/jpeg)
    jpeg_hex_pos=$(xxd -p "$down" | tr -d '\n' | grep -ob 'ffd9' | head -n1 | cut -d: -f1)
    if [ -n "$jpeg_hex_pos" ]; then
      first_byte=$((jpeg_hex_pos/2))
      tail_start=$((first_byte + 2 + 1))
      echo "JPEG FFD9 at byte $first_byte; bytes after EOF:"
      tail -c +"$tail_start" "$down" | xxd -C | head -n 40
    else
      echo "No JPEG FFD9 found"
    fi
    ;;
  image/png)
    png_hex_pos=$(xxd -p "$down" | tr -d '\n' | grep -ob '49454e44' | head -n1 | cut -d: -f1)
    if [ -n "$png_hex_pos" ]; then
      first_byte=$((png_hex_pos/2))
      tail_start=$((first_byte + 4 + 4 + 1))
      echo "PNG IEND at byte $first_byte; bytes after IEND+CRC:"
      tail -c +"$tail_start" "$down" | xxd -C | head -n 40
    else
      echo "No PNG IEND found"
    fi
    ;;
  application/pdf)
    pdf_pos=$(grep -aob '%EOF' "$down" | tail -n1 | cut -d: -f1)
    if [ -n "$pdf_pos" ]; then
      tail_start=$((pdf_pos + 4 + 1))
      echo "%EOF at byte $pdf_pos; bytes after last %EOF:"
      tail -c +"$tail_start" "$down" | xxd -C | head -n 40
    else
      echo "No %EOF found"
    fi
    ;;
  application/zip)
    zip_pos=$(xxd -p "$down" | tr -d '\n' | grep -ob '504b0506' | head -n1 | cut -d: -f1)
    if [ -n "$zip_pos" ]; then
      first_byte=$((zip_pos/2))
      tail_start=$((first_byte + 4 + 1))
      echo "ZIP EOCD at byte $first_byte; bytes after EOCD:"
      tail -c +"$tail_start" "$down" | xxd -C | head -n 40
    else
      echo "No ZIP EOCD found"
    fi
    ;;
  *)
    echo "Unknown file type ($file_type) — scanning tail generally:"
    tail -c 200 "$down" | xxd -C
    ;;
esac

echo
echo "=== DONE ==="
