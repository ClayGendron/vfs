# tier: language
# world: none
while IFS= read -r l; do printf '[%s]\n' "$l"; done <<-'EOF'
	tabbed
		twice
  spaces stay
	EOF
