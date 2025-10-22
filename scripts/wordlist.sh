#!/usr/bin/env bash

# Prerequisites:
# 1. Clone SecLists: git clone https://github.com/danielmiessler/SecLists ~/wordlists/SecLists
# 2. Download Assetnote wordlists: wget -r --no-parent -R "index.html*" https://wordlists-cdn.assetnote.io/data/ -nH -e robots=off
#    Then move the downloaded 'data' folder to ~/wordlists/assetnote
# 3. Add your custom wordlists to ~/wordlists/custom
# 4. Make executable: chmod +x wordlist.sh
# 5. Move to PATH: sudo mv wordlist.sh /usr/bin/wordlist

WORDLIST_DIR=~/wordlists
SEARCH_TERM="$1"

cd "$WORDLIST_DIR" && find . -ipath "*$SEARCH_TERM*" | sed "s|^\./|$WORDLIST_DIR/|"
