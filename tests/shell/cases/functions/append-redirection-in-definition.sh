# tier: language
# world: none
log() { echo "$*"; } >> log.txt
log first
log second
log third
while IFS= read -r line; do echo "log: $line"; done < log.txt
