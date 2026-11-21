# tier: language
# world: none
for w in a b stop c; do
  case $w in
    stop) break ;;
    *) echo "w=$w" ;;
  esac
done
echo "stopped at $w"
