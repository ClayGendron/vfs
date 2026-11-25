# tier: language
# world: none
x='dir///'
echo "${x%"${x##*[!/]}"}"
