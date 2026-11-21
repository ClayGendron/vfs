# tier: language
# world: none
arr=(one two three)
while IFS= read -r line; do echo "$line"; done <<EOF
all: ${arr[@]}
star: ${arr[*]}
second: ${arr[1]}
count: ${#arr[@]}
EOF
