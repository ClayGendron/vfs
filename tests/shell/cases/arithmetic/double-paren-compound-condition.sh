# tier: language
# world: none
a=2 b=-1
if (( a > 0 && b > 0 )); then echo both; elif (( a > 0 || b > 0 )); then echo one; fi
