# tier: language
# world: none
mapfile -t lines <<< "$(printf 'x\ny\nz\n')"
echo "n=${#lines[@]} last=${lines[2]}"
