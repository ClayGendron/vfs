# tier: language
# world: none
f() {
  local -a list=(a b c)
  local -i n=2*3
  echo "count=${#list[@]} n=$n"
}
f
echo "after: [${list[*]-unset}] [${n-unset}]"
