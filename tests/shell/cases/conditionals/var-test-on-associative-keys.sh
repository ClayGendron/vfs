# tier: language
# world: none
declare -A m=([k]=v [blank]="")
[[ -v m[k] ]]; echo "k: $?"
[[ -v m[blank] ]]; echo "blank: $?"
[[ -v m[nope] ]]; echo "nope: $?"
