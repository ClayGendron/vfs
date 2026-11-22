# tier: language
# world: none
path=/usr/local/lib/archive.tar.gz
echo "base=${path##*/}"
echo "dir=${path%/*}"
echo "ext=${path##*.}"
echo "stem=${path%.*}"
f=${path##*/}
echo "name=${f%%.*}"
