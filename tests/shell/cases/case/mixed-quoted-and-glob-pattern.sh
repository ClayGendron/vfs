# tier: language
# world: none
case "a*bc" in "a*"*) echo "quoted prefix then glob" ;; esac
case "axbc" in "a*"*) echo "never" ;; *) echo "axbc lacks a literal star" ;; esac
