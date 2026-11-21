# tier: language
# world: none
a=([1]=one [5]=five [9]=nine)
echo "count=${#a[@]}"
echo "indices=${!a[*]}"
echo "values=${a[*]}"
echo "gap=[${a[2]}]"
