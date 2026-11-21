# tier: language
# world: none
{ echo one; } > log.txt
{ echo two; echo three; } >> log.txt
mapfile -t got < log.txt
echo "${got[*]}"
