# tier: language
# world: none
echo
echo "[after]"
printf '%s\n' "$(echo)" | { IFS= read -r l; echo "len=${#l}"; }
