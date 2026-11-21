# tier: language
# world: none
case 'a\b' in 'a\b') echo "quoted backslash matched" ;; esac
case 'a\b' in a\\b) echo "escaped backslash matched" ;; esac
