# tier: language
# world: none
while IFS= read -r l; do echo "[$l]"; done <<-EOF
	tab indented
		twice
	EOF
