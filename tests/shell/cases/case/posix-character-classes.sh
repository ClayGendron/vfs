# tier: language
# world: none
for c in 7 Q q ' ' . _; do
  case $c in
    [[:digit:]]) k=digit ;;
    [[:upper:]]) k=upper ;;
    [[:lower:]]) k=lower ;;
    [[:space:]]) k=space ;;
    [[:punct:]]) k=punct ;;
    *) k=none ;;
  esac
  echo "[$c] $k"
done
