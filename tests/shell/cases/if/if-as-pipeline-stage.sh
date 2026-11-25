# tier: language
# world: none
if true; then echo piped; fi | while read -r l; do echo "got:$l"; done
