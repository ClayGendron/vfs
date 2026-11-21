# tier: language
# world: none
case "new york" in "new "*) echo "quoted space then star" ;; esac
case "new york" in new\ york) echo "escaped space" ;; esac
