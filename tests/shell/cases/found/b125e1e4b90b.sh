# tier: language
# world: none
set -- "${a^^}" x $'-7'; shift; echo "$1|$#"
IFS=" " read -r p q r <<< " b c"; echo "p=$p q=$q r=$r"
for v in 1 2 3 4; do if (( v == 1 )); then break; fi; echo "c:$v"; done; echo "after=$v"
b="${b//t?o/R}"
if [[ "$(echo two)" =~ x-?y ]]; then echo "m=${BASH_REMATCH[0]}|${BASH_REMATCH[1]}"; else echo nomatch; fi
: > c d; : > b.txt; : > a.txt; shopt -s failglob; for f in .*; do echo "g:$f"; done; shopt -u nullglob dotglob failglob
