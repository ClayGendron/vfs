# tier: language
# world: none
case "${b-dflt}" in ?) echo arm0;; *) echo none;; esac
set -- ; echo "${@:2}"
x=$(( (2 - ((x ^ x) && (2 && x))) )); echo "x=$x"
for v in 1 2 3 4; do if (( v == 2 )); then break 1; fi; echo "c:$v"; done; echo "after=$v"
f() { local s="$1"; echo -n ${b%%*} "3"; echo; : > ab; : > a.txt; : > b.txt; shopt -s failglob; for f in .*; do echo "g:$f"; done; shopt -u nullglob dotglob failglob; echo "args=$#"; return 3; }; f "${x%%*/*}" $(( ((i + -3) & ((-3 % (0 == 0 ? 1 : 0)) != 1)) )); echo "ret=$?"
f() { local s="$1"; echo "$x" | { read -r first; echo "first=$first"; }; echo "pipe=$?"; echo "args=$#"; return 3; }; f ; echo "ret=$?"
b=$(( -3 )); echo "b=$b"
n0=0; while (( n0 < 1 )); do n0=$((n0 + 1)); f() { local s="$1"; declare -A m=(["x y"]="${s:-dflt}" ["k"]=a.b ["3"]=${i^^}); echo "${#m[@]}"; echo "args=$#"; return 3; }; f ; echo "ret=$?"; printf -v a '%s-%s' ${s:1:2} "$(( (i != x) ))"; echo "$x"; echo one two | { read -r l; echo "$l"; }; echo "pipe=$?"; done; echo "n0=$n0"
