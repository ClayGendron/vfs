# tier: language
# world: none
grade() {
  if [[ $1 == *[!0-9]* ]]; then echo "$1: not a number"
  elif [[ $1 -ge 90 ]]; then echo "$1: A"
  elif [[ $1 -ge 80 ]]; then echo "$1: B"
  else echo "$1: C"
  fi
}
grade 95; grade 85; grade 70; grade 8x
