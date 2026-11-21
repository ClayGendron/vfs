# tier: language
# world: seed
files=(logs/*.log)
[ -e "${files[0]}" ] && echo "have logs: ${#files[@]}"
files=(logs/*.gz)
[ -e "${files[0]}" ] || echo "no gz: [${files[0]}]"
