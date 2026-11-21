# tier: language
# world: none
: > a.txt
: > b.txt
[[ a.txt -ef a.txt ]]; echo "a -ef a: $?"
[[ a.txt -ef ./a.txt ]]; echo "a -ef ./a: $?"
[[ a.txt -ef b.txt ]]; echo "a -ef b: $?"
[[ a.txt -ef missing ]]; echo "a -ef missing: $?"
