# tier: language
# world: none
{ echo first; echo second; } > out.txt
mapfile -t got < out.txt
echo "${#got[@]} lines: ${got[*]}"
