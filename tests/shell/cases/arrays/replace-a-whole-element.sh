# tier: language
# world: none
a=(one two three)
echo "${a[@]/*/X}"
echo "${a[@]/#*/[&]}"
