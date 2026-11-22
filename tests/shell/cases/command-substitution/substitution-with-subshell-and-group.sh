# tier: language
# world: none
x=$( { echo group; } ; ( echo sub ) )
printf '[%s]\n' "$x"
