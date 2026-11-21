# tier: language
# world: none
i=0
while [ "$i" -lt 2 ]; do i=$((i + 1)); (exit 7); done
echo "status=$?"
