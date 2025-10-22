# Use after downloading target's static files using staticdl
# ./generate_localhost_urls.py -p staticdl/ -o download.txt
# cd staticdl/ && python -m http.server 8888
# cat download.txt | nuclei -t http/exposures/tokens

import os
import sys
from pathlib import Path

args = sys.argv[1:]
dir_path = args[args.index('-p') + 1]
output = args[args.index('-o') + 1] if '-o' in args else 'file_urls.txt'

dir_path = Path(dir_path).resolve()
file_urls = []

for root, dirs, files in os.walk(dir_path):
    for file in files:
        file_path = Path(root) / file
        relative_path = file_path.relative_to(dir_path)
        url_path = str(relative_path).replace('\\', '/')
        file_urls.append(f"https://localhost:8888/{url_path}")

file_urls.sort()

with open(output, 'w') as f:
    for url in file_urls:
        f.write(url + '\n')

print(f"{len(file_urls)} URLs saved to {output}")
