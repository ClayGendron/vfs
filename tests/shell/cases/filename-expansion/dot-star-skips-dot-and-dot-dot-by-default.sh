# tier: language
# world: seed
set -- .*
echo "count=$#"
for f; do [ "$f" = . ] || [ "$f" = .. ] && echo "found $f"; done
echo "checked"
