# tier: language
# world: none
x='a "b" $c `d` \e'
declare -p x
y=$'tab\there'
declare -p y
