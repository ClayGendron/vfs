# tier: language
# world: seed
files=(docs/*.nothing)
echo "count=${#files[@]} first=[${files[0]}]"
shopt -s nullglob
files=(docs/*.nothing)
echo "with nullglob count=${#files[@]}"
