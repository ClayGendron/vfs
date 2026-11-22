# tier: language
# world: none
read -a raw_off <<< 'a\ b c\\d'
read -r -a raw_on <<< 'a\ b c\\d'
printf 'without -r: '; printf '[%s]' "${raw_off[@]}"; echo
printf 'with -r: '; printf '[%s]' "${raw_on[@]}"; echo
