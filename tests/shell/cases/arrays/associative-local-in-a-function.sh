# tier: language
# world: none
f() {
  local -A cfg=([mode]=fast)
  cfg[level]=3
  echo "mode=${cfg[mode]} level=${cfg[level]}"
}
f
echo "outside=[${cfg[mode]-unset}]"
