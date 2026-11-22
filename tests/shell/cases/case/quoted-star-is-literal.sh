# tier: language
# world: none
for w in '*' anything; do
  case $w in
    "*") echo "[$w] matched quoted star" ;;
    *) echo "[$w] matched glob star" ;;
  esac
done
