# tier: language
# world: none
z=0
echo $(( z != 0 && 10 / z ))
echo $(( z == 0 ? 0 : 10 / z ))
