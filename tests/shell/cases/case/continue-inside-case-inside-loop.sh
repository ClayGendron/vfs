# tier: language
# world: none
for w in a skip b; do
  case $w in skip) continue ;; esac
  echo "w=$w"
done
