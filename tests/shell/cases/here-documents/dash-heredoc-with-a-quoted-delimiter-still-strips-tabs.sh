# tier: language
# world: none
v=x
while IFS= read -r line; do echo "[$line]"; done <<-'EOF'
	literal $v
	EOF
