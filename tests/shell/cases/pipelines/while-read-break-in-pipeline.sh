# tier: language
# world: none
printf '%s\n' 1 2 3 4 | while read -r n; do
  [ "$n" = 3 ] && break
  echo "n=$n"
done
echo "status=$?"
