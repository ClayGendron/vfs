# tier: language
# world: seed
for f in *.txt; do echo "file=[$f]"; done
set -- *.txt
echo "count=$#"
