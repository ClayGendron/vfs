# tier: language
# world: none
while read -r w; do echo "w=$w"; done < <(while read -r a b; do echo "$b"; echo "$a"; done <<< "left right")
