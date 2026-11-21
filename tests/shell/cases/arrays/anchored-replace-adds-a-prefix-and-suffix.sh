# tier: language
# world: none
a=(one two)
printf '[%s]' "${a[@]/#/--}"; echo
printf '[%s]' "${a[@]/%/.txt}"; echo
printf '[%s]' "${a[@]/#t/T}"; echo
