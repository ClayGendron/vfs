# tier: language
# world: none
first_negative() {
  while read -r n; do
    if [ "$n" -lt 0 ]; then echo "$n"; return 0; fi
  done
  return 1
}
first_negative <<< $'3\n-2\n-5'
echo "status=$?"
