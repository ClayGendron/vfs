# tier: language
# world: none
exec 3<<< "via fd three"
read -u 3 x
echo "x=[$x]"
exec 3<&-
