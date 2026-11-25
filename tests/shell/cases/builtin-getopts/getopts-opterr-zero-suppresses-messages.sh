# tier: language
# world: none
OPTERR=0
set -- -z -f
getopts f: opt
echo "first: opt=$opt"
getopts f: opt
echo "second: opt=$opt"
