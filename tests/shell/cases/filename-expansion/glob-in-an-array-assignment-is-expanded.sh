# tier: language
# world: seed
files=(docs/*.md)
echo "count=${#files[@]}"
printf '[%s]\n' "${files[@]}"
