# tier: language
# world: none
exec 4<<< $'fd1\nfd2'
mapfile -t -u 4 arr
exec 4<&-
echo "${arr[*]}"
