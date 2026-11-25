# tier: language
# world: none
while read -r l; do
  read -r other <<< "here-$l"
  echo "$l $other"
done < <(printf '1\n2\n')
