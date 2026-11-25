# tier: language
# world: none
x=$(
  echo one
  echo two
)
printf '[%s]\n' "$x"
