// Parse every corpus command with mvdan.cc/sh/v3 under the bash and POSIX
// dialects; print one JSON line per (id, dialect) with ok/error/position.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"mvdan.cc/sh/v3/syntax"
)

type row struct {
	ID       int      `json:"id"`
	Features []string `json:"features"`
	Cmd      string   `json:"cmd"`
}

type out struct {
	ID      int    `json:"id"`
	Dialect string `json:"dialect"`
	OK      bool   `json:"ok"`
	Error   string `json:"error,omitempty"`
	Nodes   int    `json:"nodes,omitempty"`
}

func main() {
	f, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	enc := json.NewEncoder(os.Stdout)
	for sc.Scan() {
		var r row
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			panic(err)
		}
		for _, v := range []syntax.LangVariant{syntax.LangBash, syntax.LangPOSIX} {
			p := syntax.NewParser(syntax.Variant(v), syntax.KeepComments(true))
			file, err := p.Parse(strings.NewReader(r.Cmd), "cmd")
			o := out{ID: r.ID, Dialect: v.String()}
			if err != nil {
				o.Error = err.Error()
			} else {
				o.OK = true
				n := 0
				syntax.Walk(file, func(syntax.Node) bool { n++; return true })
				o.Nodes = n
			}
			enc.Encode(o)
		}
	}
	fmt.Fprintln(os.Stderr, "done")
}
