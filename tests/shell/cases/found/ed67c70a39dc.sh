# tier: language
# world: none
IFS="-" read -r p q r <<< ""; echo "p=$p q=$q r=$r"
printf -v s '%s-%s' 'one' 'one'; echo "$x"
while read -r l; do echo "h:$l"; done <<'EOF'
"${arr[@]}" ${!arr[@]}
plain $x
EOF
printf '%q\n' 'a/b/c' "a/b/c" $'two words'; echo
{ : > .hidden; : > b.txt; : > c d; shopt -s dotglob; for f in ?b; do echo "g:$f"; done; shopt -u nullglob dotglob failglob; : > c d; : > a.txt; : > ab; for f in *.txt; do echo "g:$f"; done; shopt -u nullglob dotglob failglob; arr=("${i##*b}" 3 "${!arr[@]}" two); unset 'arr[1]'; printf '<%s>' "${arr[@]}"; echo " ${#arr[@]}"; } > out.txt; while read -r l; do echo "r:$l"; done < out.txt
( printf '%s %s\n' one; echo; : > a.txt; : > .hidden; : > b.txt; shopt -s nullglob; for f in *; do echo "g:$f"; done; shopt -u nullglob dotglob failglob; x=inner ); echo "x=$x"
