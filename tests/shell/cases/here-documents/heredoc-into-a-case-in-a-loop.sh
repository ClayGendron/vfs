# tier: language
# world: none
while read -r word; do
  case $word in
    a*) echo "$word starts with a" ;;
    *) echo "$word other" ;;
  esac
done <<EOF
apple
pear
EOF
