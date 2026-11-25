# tier: language
# world: none
f() { read -r a; echo "f read [$a]"; }
f <<< "argument via stdin"
