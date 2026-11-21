# tier: language
# world: none
if echo hi > nodir/x; then
  echo "then branch"
else
  echo "else branch status=$?"
fi
