# tier: language
# world: none
v=; unset v
echo "${v-a\nb}" "${v:-c\qd}"
echo ${v-a\nb} "${v:+x}"
