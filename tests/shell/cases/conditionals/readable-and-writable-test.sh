# tier: language
# world: none
echo x > mine.txt
[[ -r mine.txt ]]; echo "-r: $?"
[[ -w mine.txt ]]; echo "-w: $?"
[[ -x mine.txt ]]; echo "-x: $?"
[[ -r missing.txt ]]; echo "-r missing: $?"
