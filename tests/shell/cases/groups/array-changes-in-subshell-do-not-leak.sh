# tier: language
# world: none
arr=(1 2)
(arr+=(3); echo "inside: ${#arr[@]}")
echo "outside: ${#arr[@]}"
