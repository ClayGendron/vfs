# tier: language
# world: none
f() { echo "line from f"; echo "error from f" >&2; }
f > out.txt 2> err.txt
IFS= read -r o < out.txt
IFS= read -r e < err.txt
echo "out=[$o] err=[$e]"
