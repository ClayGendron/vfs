# tier: language
# world: none
f() {
  for i in 1 2 3; do
    for j in a b; do
      if [ "$i$j" = 2a ]; then return 7; fi
      echo "$i$j"
    done
  done
}
f
echo "status=$?"
