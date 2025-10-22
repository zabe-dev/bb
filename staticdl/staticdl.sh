#!/usr/bin/env bash

VERSION="1.0"
START_TIME=0
INTERRUPTED=0
MAX_SIZE=$((10 * 1024 * 1024))

CYAN='\033[96m'
GREEN='\033[92m'
ORANGE='\033[93m'
RED='\033[91m'
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

TOTAL_URLS=0
DOWNLOADED=0
FAILED=0
DUPLICATES=0
REDIRECTS=0
SIZE_EXCEEDED=0
CLEANUP_DIR=""

declare -A HASH_MAP
declare -A REDIRECT_MAP

print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
     _        _   _          _ _
 ___| |_ __ _| |_(_) ___ __| | |
/ __| __/ _` | __| |/ __/ _` | |
\__ \ || (_| | |_| | (_| (_| | |
|___/\__\__,_|\__|_|\___\__,_|_|
EOF
    echo -e "${RESET}"
    echo -e "${DIM}    Static File Downloader v${VERSION}${RESET}"
    echo ""
}

cleanup() {
    printf "\r\033[K"
    find "${CLEANUP_DIR:-/tmp}" -name "*.tmp" -o -name "*.headers" 2>/dev/null | while read -r f; do
        [[ -f "$f" ]] && rm -f "$f"
    done
}

signal_handler() {
    INTERRUPTED=1
    cleanup
    local elapsed=$(($(date +%s) - START_TIME))
    echo -e "\n[${ORANGE}WRN${RESET}] Download interrupted (${elapsed}s time elapsed)"
    print_summary
    exit 130
}

trap signal_handler SIGINT SIGTERM
trap cleanup EXIT

log_info() {
    echo -e "[${CYAN}INF${RESET}] $1"
}

log_success() {
    return 0
}

log_warning() {
    echo -e "[${ORANGE}WRN${RESET}] $1"
}

log_error() {
    return 0
}

log_skip() {
    return 0
}

update_progress() {
    echo -ne "\rDownloading files... ${DIM}($TOTAL_URLS processed, $DOWNLOADED downloaded)${RESET}"
}

check_dependencies() {
    local missing=()
    local use_aria2=0

    if command -v aria2c &> /dev/null; then
        use_aria2=1
    elif command -v curl &> /dev/null; then
        use_aria2=0
    else
        missing+=("curl or aria2c")
    fi

    for cmd in file sha256sum; do
        if ! command -v "$cmd" &> /dev/null; then
            if [[ "$cmd" == "sha256sum" ]] && command -v shasum &> /dev/null; then
                continue
            fi
            missing+=("$cmd")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        exit 1
    fi

    echo "$use_aria2"
}

calculate_hash() {
    local filepath="$1"
    local hash

    if command -v sha256sum &> /dev/null; then
        hash=$(sha256sum "$filepath" 2>/dev/null | awk '{print $1}')
    elif command -v shasum &> /dev/null; then
        hash=$(shasum -a 256 "$filepath" 2>/dev/null | awk '{print $1}')
    else
        echo ""
        return 1
    fi

    echo "$hash"
}

load_existing_hashes() {
    local output_dir="$1"

    if [[ ! -d "$output_dir" ]]; then
        return 0
    fi

    while IFS= read -r filepath; do
        local hash=$(calculate_hash "$filepath")
        if [[ -n "$hash" ]]; then
            local filename=$(basename "$filepath")
            HASH_MAP["$hash"]="$filename"
        fi
    done < <(find "$output_dir" -type f -not -name "*.tmp" -not -name "*.headers" 2>/dev/null)
}

get_filename_from_url() {
    local url="$1"
    local filename

    filename=$(basename "$url" | cut -d'?' -f1)

    if [[ -z "$filename" ]] || [[ "$filename" == "/" ]]; then
        filename="index.html"
    fi

    echo "$filename"
}

detect_file_type() {
    local filepath="$1"
    local filetype

    if command -v file &> /dev/null; then
        filetype=$(file -b --mime-type "$filepath" 2>/dev/null)
        echo "$filetype"
    else
        echo "unknown"
    fi
}

format_size() {
    local bytes=$1

    if [[ $bytes -lt 1024 ]]; then
        echo "${bytes}B"
    elif [[ $bytes -lt $((1024 * 1024)) ]]; then
        echo "$((bytes / 1024))KB"
    else
        echo "$((bytes / 1024 / 1024))MB"
    fi
}

download_file() {
    local url="$1"
    local output_dir="$2"
    local filename="$3"
    local use_aria2="$4"
    local filepath="${output_dir}/${filename}"
    local temp_file="${filepath}.tmp"

    if [[ -n "${REDIRECT_MAP[$url]}" ]]; then
        log_skip "[${ORANGE}REDIRECT${RESET}] $filename -> ${REDIRECT_MAP[$url]}"
        ((REDIRECTS++))
        return 0
    fi

    if [[ -f "$filepath" ]]; then
        local existing_hash=$(calculate_hash "$filepath")
        if [[ -n "$existing_hash" ]] && [[ -n "${HASH_MAP[$existing_hash]}" ]]; then
            log_skip "[${ORANGE}DUPLICATE${RESET}] $filename"
            ((DUPLICATES++))
            return 0
        else
            local counter=1
            local base_filename="${filename%.*}"
            local extension="${filename##*.}"
            if [[ "$base_filename" == "$extension" ]]; then
                while [[ -f "${output_dir}/${filename}_${counter}" ]]; do
                    ((counter++))
                done
                filename="${filename}_${counter}"
            else
                while [[ -f "${output_dir}/${base_filename}_${counter}.${extension}" ]]; do
                    ((counter++))
                done
                filename="${base_filename}_${counter}.${extension}"
            fi
            filepath="${output_dir}/${filename}"
            temp_file="${filepath}.tmp"
        fi
    fi

    local temp_headers="${temp_file}.headers"
    local exit_code=0

    if [[ $use_aria2 -eq 1 ]]; then
        aria2c --console-log-level=error \
               --summary-interval=0 \
               --download-result=hide \
               -x 16 \
               -s 16 \
               -k 1M \
               --max-tries=2 \
               --retry-wait=1 \
               --timeout=300 \
               --connect-timeout=30 \
               --max-file-not-found=0 \
               --allow-overwrite=true \
               --auto-file-renaming=false \
               --file-allocation=none \
               -d "$output_dir" \
               -o "$(basename "$temp_file")" \
               "$url" &> /dev/null
        exit_code=$?

        if [[ $exit_code -eq 0 ]] && [[ -f "$temp_file" ]]; then
            local size=$(stat -f%z "$temp_file" 2>/dev/null || stat -c%s "$temp_file" 2>/dev/null || echo 0)

            if [[ $size -gt $MAX_SIZE ]]; then
                rm -f "$temp_file"
                log_skip "[${ORANGE}SIZE_EXCEEDED${RESET}] $filename (exceeds $(format_size $MAX_SIZE))"
                ((SIZE_EXCEEDED++))
                return 0
            fi

            if [[ $size -gt 0 ]]; then
                local hash=$(calculate_hash "$temp_file")

                if [[ -n "$hash" ]] && [[ -n "${HASH_MAP[$hash]}" ]]; then
                    rm -f "$temp_file"
                    local duplicate="${HASH_MAP[$hash]}"
                    REDIRECT_MAP["$url"]="$duplicate"
                    log_skip "[${ORANGE}DUPLICATE${RESET}] $filename -> ${duplicate}"
                    ((DUPLICATES++))
                    return 0
                fi

                mv "$temp_file" "$filepath"

                if [[ -n "$hash" ]]; then
                    HASH_MAP["$hash"]="$filename"
                    REDIRECT_MAP["$url"]="$filename"
                fi

                local filetype=$(detect_file_type "$filepath")
                local size_formatted=$(format_size $size)
                log_success "Downloaded $filename ($size_formatted, $filetype)"
                ((DOWNLOADED++))
                return 0
            else
                rm -f "$temp_file"
                log_error "Download failed $filename (empty file)"
                ((FAILED++))
                return 1
            fi
        else
            rm -f "$temp_file"
            log_error "Download failed $filename"
            ((FAILED++))
            return 1
        fi
    else
        curl -sS -L --max-time 300 --retry 2 --retry-delay 1 \
             --max-filesize "$MAX_SIZE" --parallel --parallel-max 5 \
             -D "$temp_headers" -o "$temp_file" "$url" 2>/dev/null
        exit_code=$?

        if [[ $exit_code -eq 63 ]]; then
            rm -f "$temp_file" "$temp_headers"
            log_skip "[${ORANGE}SIZE_EXCEEDED${RESET}] $filename (exceeds $(format_size $MAX_SIZE))"
            ((SIZE_EXCEEDED++))
            return 0
        fi

        if [[ $exit_code -eq 0 ]] && [[ -f "$temp_file" ]] && [[ -f "$temp_headers" ]]; then
            local final_url=$(grep -i "^location:" "$temp_headers" | tail -1 | sed 's/^[Ll]ocation: *//;s/\r$//' | xargs)

            if [[ -z "$final_url" ]]; then
                final_url="$url"
            fi

            if [[ "$final_url" != "$url" ]] && [[ -n "${REDIRECT_MAP[$final_url]}" ]]; then
                rm -f "$temp_file" "$temp_headers"
                local redirect_to="${REDIRECT_MAP[$final_url]}"
                REDIRECT_MAP["$url"]="$redirect_to"
                log_skip "[${ORANGE}REDIRECT${RESET}] $filename -> ${redirect_to}"
                ((REDIRECTS++))
                return 0
            fi

            local size=$(stat -f%z "$temp_file" 2>/dev/null || stat -c%s "$temp_file" 2>/dev/null || echo 0)

            if [[ $size -gt 0 ]]; then
                local hash=$(calculate_hash "$temp_file")

                if [[ -n "$hash" ]] && [[ -n "${HASH_MAP[$hash]}" ]]; then
                    rm -f "$temp_file" "$temp_headers"
                    local duplicate="${HASH_MAP[$hash]}"
                    REDIRECT_MAP["$url"]="$duplicate"
                    if [[ "$final_url" != "$url" ]]; then
                        REDIRECT_MAP["$final_url"]="$duplicate"
                    fi
                    log_skip "[${ORANGE}DUPLICATE${RESET}] $filename -> ${duplicate}"
                    ((DUPLICATES++))
                    return 0
                fi

                mv "$temp_file" "$filepath"
                rm -f "$temp_headers"

                if [[ -n "$hash" ]]; then
                    HASH_MAP["$hash"]="$filename"
                    REDIRECT_MAP["$url"]="$filename"
                    if [[ "$final_url" != "$url" ]]; then
                        REDIRECT_MAP["$final_url"]="$filename"
                    fi
                fi

                local filetype=$(detect_file_type "$filepath")
                local size_formatted=$(format_size $size)
                log_success "Downloaded $filename ($size_formatted, $filetype)"
                ((DOWNLOADED++))
                return 0
            else
                rm -f "$temp_file" "$temp_headers"
                log_error "Download failed $filename (empty file)"
                ((FAILED++))
                return 1
            fi
        else
            rm -f "$temp_file" "$temp_headers"
            log_error "Download failed $filename"
            ((FAILED++))
            return 1
        fi
    fi
}

process_urls() {
    local url_file="$1"
    local output_dir="$2"
    local use_aria2="$3"

    update_progress

    while IFS= read -r url || [[ -n "$url" ]]; do
        url=$(echo "$url" | xargs)

        if [[ -z "$url" ]] || [[ "$url" == \#* ]]; then
            continue
        fi

        ((TOTAL_URLS++))

        local filename=$(get_filename_from_url "$url")
        download_file "$url" "$output_dir" "$filename" "$use_aria2"

        update_progress

        if [[ $INTERRUPTED -eq 1 ]]; then
            break
        fi

    done < "$url_file"

    printf "\r\033[K"
}

print_summary() {
    echo ""
    log_info "Download Summary:"
    echo -e "  Total URLs:      ${TOTAL_URLS}"
    echo -e "  ${GREEN}Downloaded:${RESET}      ${DOWNLOADED}"
    echo -e "  ${ORANGE}Duplicates:${RESET}      ${DUPLICATES}"
    echo -e "  ${ORANGE}Redirects:${RESET}       ${REDIRECTS}"
    echo -e "  ${ORANGE}Size exceeded:${RESET}   ${SIZE_EXCEEDED}"
    echo -e "  ${RED}Failed:${RESET}          ${FAILED}"
}

show_usage() {
    cat << EOF
Usage: staticdl -f <urls.txt> -o <output/> [options]

Options:
  -f <file>        File containing URLs (one per line)
  -o <dir>         Output directory for downloaded files
  -max <bytes>     Maximum file size in bytes (default: 10MB)
  -h               Show this help message

Download Engine:
  Automatically uses aria2c if available for faster downloads with
  16 connections per file. Falls back to curl if aria2c not found.

Examples:
  staticdl -f urls.txt -o downloads/
  staticdl -f urls.txt -o public/
  staticdl -f urls.txt -o assets/ -max 5242880
  staticdl -f urls.txt -o files/ -max $((20 * 1024 * 1024))

EOF
}

main() {
    local url_file=""
    local output_dir=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -f)
                url_file="$2"
                shift 2
                ;;
            -o)
                output_dir="$2"
                shift 2
                ;;
            -max)
                MAX_SIZE="$2"
                shift 2
                ;;
            -h)
                show_usage
                exit 0
                ;;
            *)
                show_usage
                exit 1
                ;;
        esac
    done

    if [[ -z "$url_file" ]] || [[ -z "$output_dir" ]]; then
        log_error "Missing required arguments"
        show_usage
        exit 1
    fi

    if [[ ! -f "$url_file" ]]; then
        log_error "URL file not found: $url_file"
        exit 1
    fi

    print_banner
    START_TIME=$(date +%s)

    log_info "Checking dependencies..."
    local use_aria2=$(check_dependencies)

    if [[ $use_aria2 -eq 1 ]]; then
        log_info "Using aria2c for faster downloads"
    else
        log_info "Using curl (install aria2c for faster downloads)"
    fi

    mkdir -p "$output_dir"
    CLEANUP_DIR="$output_dir"

    log_info "URL file: $url_file"
    log_info "Output directory: $output_dir"
    log_info "Max file size: $(format_size $MAX_SIZE)"

    load_existing_hashes "$output_dir"
    echo ""

    process_urls "$url_file" "$output_dir" "$use_aria2"

    cleanup

    local elapsed=$(($(date +%s) - START_TIME))

    print_summary
    echo ""
    log_info "Files saved to: $output_dir"
    log_info "Download finished (${elapsed}s time elapsed)"
    echo ""
}

main "$@"
