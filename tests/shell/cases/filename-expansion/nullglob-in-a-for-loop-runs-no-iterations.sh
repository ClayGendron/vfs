# tier: language
# world: seed
shopt -s nullglob
n=0
for f in *.nomatch; do n=$((n+1)); done
echo "iterations=$n"
