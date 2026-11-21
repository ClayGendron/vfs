# tier: language
# world: none
set -C
echo a >new.txt
echo b >>new.txt
echo "status=$?"
while IFS= read -r l; do echo "line=$l"; done <new.txt
