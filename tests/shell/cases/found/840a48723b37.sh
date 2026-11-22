# tier: language
# world: none
case ${arr[@]} in *b) echo arm0;; */*) echo arm1;; *) echo none;; esac
while read -r l; do echo "h:$l"; done <<'EOF'
${i%%?} $a
plain $x
EOF
x="${a##o*e}"
( n1=0; while (( n1 < 4 )); do n1=$((n1 + 1)); arr=('-7' ${x//*/*/R} ${#arr[@]}); unset 'arr[1]'; printf '<%s>' "${arr[@]}"; echo " ${#arr[@]}"; arr=("${i:+alt}"); printf '<%s>' "${arr[@]}"; echo " ${#arr[@]}"; if [[ "${#i}" =~ ^[^x]* ]]; then echo "m=${BASH_REMATCH[0]}|${BASH_REMATCH[1]}"; else echo nomatch; fi; done; echo "n1=$n1"; x=inner ); echo "x=$x"
