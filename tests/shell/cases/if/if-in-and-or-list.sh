# tier: language
# world: none
if true; then echo a; fi && echo "if succeeded"
if true; then false; fi || echo "if failed"
