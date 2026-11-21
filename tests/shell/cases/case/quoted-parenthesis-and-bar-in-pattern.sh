# tier: language
# world: none
for w in 'a|b' '(x)'; do
  case $w in
    'a|b') echo "[$w] literal bar" ;;
    \(x\)) echo "[$w] literal parens" ;;
  esac
done
