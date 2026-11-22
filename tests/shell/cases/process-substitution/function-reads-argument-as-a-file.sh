# tier: language
# world: none
count_lines() {
  local n=0
  while IFS= read -r _; do n=$((n + 1)); done < "$1"
  echo "$n"
}
echo "lines: $(count_lines <(printf 'x\ny\nz\n'))"
