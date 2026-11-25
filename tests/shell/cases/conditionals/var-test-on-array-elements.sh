# tier: language
# world: none
a=([1]=x [3]="")
[[ -v a ]]; echo "a (element 0): $?"
[[ -v a[1] ]]; echo "a[1]: $?"
[[ -v a[3] ]]; echo "a[3] empty: $?"
[[ -v a[2] ]]; echo "a[2]: $?"
[[ -v a[@] ]]; echo "a[@]: $?"
