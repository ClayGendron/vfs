# tier: language
# world: none
x=5 y=0
if [ "$x" -gt 0 ]; then
  if [ "$y" -gt 0 ]; then
    echo "both positive"
  else
    echo "x positive, y not"
  fi
fi
