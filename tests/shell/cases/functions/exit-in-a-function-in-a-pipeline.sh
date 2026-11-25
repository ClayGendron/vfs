# tier: language
# world: none
f() { echo piped; exit 5; }
f | while read -r l; do echo "read $l"; done
echo "status=$?"
f | true
echo "pipestatus=${PIPESTATUS[*]}"
