# tier: language
# world: none
files=("my file.txt" "other.txt")
for f in "${files[@]}"; do echo "quoted: [$f]"; done
for f in ${files[@]}; do echo "unquoted: [$f]"; done
