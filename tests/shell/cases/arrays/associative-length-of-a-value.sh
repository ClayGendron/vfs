# tier: language
# world: none
declare -A m=([word]=hello [empty]="")
echo "${#m[word]} ${#m[empty]} ${#m[nothing]}"
