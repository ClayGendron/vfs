# tier: language
# world: none
f() {
  local -A m=([one]=1 [two]=2)
  echo "one=${m[one]} two=${m[two]} n=${#m[@]}"
}
f
echo "outside: [${m[one]-unset}]"
