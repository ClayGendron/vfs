# tier: language
# world: none
gen() { echo one; echo two; echo three; }
gen | while IFS= read -r w; do echo "got $w"; done
