# tier: language
# world: none
x=set
echo "${x:?unused}"
f() { echo "${missing:?is required}"; echo "not reached in f"; }
(f)
echo "status=$?"
