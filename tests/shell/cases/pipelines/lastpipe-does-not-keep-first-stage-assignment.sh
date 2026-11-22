# tier: language
# world: none
shopt -s lastpipe
a=0 b=0
{ a=1; echo x; } | { read -r _; b=1; }
echo "a=$a b=$b"
