# tier: language
# world: none
{ echo "to group file"; echo "to inner file" > inner.txt; } > group.txt
read -r g < group.txt; read -r i < inner.txt
echo "group=[$g] inner=[$i]"
