# tier: language
# world: none
join_by() { local IFS=$1; shift; echo "$*"; }
join_by , a b c
join_by '|' "x y" z
join_by '' p q
