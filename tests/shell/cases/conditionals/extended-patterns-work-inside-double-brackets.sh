# tier: language
# world: none
f=photo.jpeg
[[ $f == *.@(jpg|jpeg|png) ]]; echo "@(...): $?"
[[ $f == !(*.png) ]]; echo "!(...): $?"
[[ aaa == +(a) ]]; echo "+(a): $?"
[[ "" == ?(x) ]]; echo "?(x) on empty: $?"
