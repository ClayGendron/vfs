# tier: language
# world: none
unset u
e=
if [[ -v u ]]; then echo "u set"; else echo "u unset"; fi
if [[ -v e ]]; then echo "e set though empty"; fi
