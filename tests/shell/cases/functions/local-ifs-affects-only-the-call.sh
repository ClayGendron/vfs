# tier: language
# world: none
split() { local IFS=:; set -- $1; echo "n=$# second=$2"; }
split "a:b:c"
s="x:y"
set -- $s
echo "outside n=$#"
