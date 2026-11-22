# tier: language
# world: none
echo hi | { read -r l; echo "got $l"; exit 3; }
echo "pipeline status=$?"
