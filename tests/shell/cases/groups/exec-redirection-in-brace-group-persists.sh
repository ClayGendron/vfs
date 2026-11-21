# tier: language
# world: none
{ exec 3> fd3.txt; }
echo "via fd 3" >&3
exec 3>&-
read -r l < fd3.txt
echo "file: $l"
