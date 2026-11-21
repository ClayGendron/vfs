# tier: language
# world: none
readarray -t lines <<< $'x\ny'
echo "count=${#lines[@]} last=${lines[-1]}"
