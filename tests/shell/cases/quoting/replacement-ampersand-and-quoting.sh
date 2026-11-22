# tier: language
# world: none
x=aXb
echo "${x/X/&&}"
echo "${x/X/\&}"
echo ${x/X/'&'}
echo "${x/X/[&]}"
