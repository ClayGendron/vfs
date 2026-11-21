# tier: language
# world: none
upper_count() { local n=0 line; while IFS= read -r line; do n=$(( n + 1 )); echo "${line^^}"; done; echo "lines=$n"; }
printf 'a\nbb\nccc\n' | upper_count
