# tier: language
# world: none
x=123abc456
echo "${x#[0-9]} ${x##*[0-9]} ${x%[0-9]} ${x%%[a-z]*}"
