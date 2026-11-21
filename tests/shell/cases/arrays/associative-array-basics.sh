# tier: language
# world: none
declare -A color
color[apple]=red
color[banana]=yellow
echo "apple=${color[apple]} banana=${color[banana]}"
echo "count=${#color[@]}"
