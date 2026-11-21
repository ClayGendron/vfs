# tier: language
# world: none
printf '%s\n' alpha beta > list.txt
while IFS= read -r l; do echo "<$l>"; done < list.txt
