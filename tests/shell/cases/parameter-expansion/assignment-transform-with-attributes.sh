# tier: language
# world: none
declare -i n=5
declare -x e=exported
declare -r r=fixed
echo "${n@A}"
echo "${e@A}"
echo "${r@A}"
