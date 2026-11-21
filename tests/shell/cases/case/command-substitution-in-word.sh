# tier: language
# world: none
case $(echo "  padded  ") in padded) echo "trimmed" ;; "  padded  ") echo "spaces kept: the word is not split" ;; esac
case "$(printf 'x\n\n')" in x) echo "trailing newlines removed" ;; esac
