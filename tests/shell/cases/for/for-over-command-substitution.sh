# tier: language
# world: none
for w in $(echo "a  b"; echo c); do printf '[%s]\n' "$w"; done
