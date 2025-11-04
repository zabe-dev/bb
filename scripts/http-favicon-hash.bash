curl -s 'https://example.com/favicon.ico' | base64 | python3 -c 'import mmh3,sys;print(mmh3.hash(sys.stdin.buffer.read()))'
