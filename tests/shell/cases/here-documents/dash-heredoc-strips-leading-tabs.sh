# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<-EOF
	one tab
		two tabs
no tab
	EOF
