# tier: language
# world: none
fruits=(apple pear)
veg=(leek)
for name in fruits veg; do
  declare -n cur=$name
  echo "$name: ${#cur[@]} -> ${cur[*]}"
done
