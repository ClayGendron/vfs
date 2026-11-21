# tier: language
# world: none
f() {
	while IFS= read -r line; do
		echo "[$line]"
	done <<-END
		indented body
		second line
	END
}
f
