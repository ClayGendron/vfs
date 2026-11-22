# tier: language
# world: none
gen() { echo one; echo two; }
gen | while read -r w; do echo "[$w]"; done
