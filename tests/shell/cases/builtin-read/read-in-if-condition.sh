# tier: language
# world: none
if read -r x <<< "yes"; then echo "read ok: $x"; fi
: > empty.txt
if ! read -r y < empty.txt; then echo "read failed: [$y]"; fi
