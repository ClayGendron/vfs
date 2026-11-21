# tier: language
# world: none
if true; then echo first; echo second; fi > out.txt
mapfile -t lines < out.txt
echo "lines=${#lines[@]} last=${lines[1]}"
