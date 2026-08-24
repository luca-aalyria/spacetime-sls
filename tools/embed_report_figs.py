#!/usr/bin/env python3
"""Produce a self-contained Markdown report with base64-embedded images.

The tool reads a Markdown file, replaces every local image reference
(`![alt](figs/name.png)`) with a `data:image/png;base64,...` URI, and writes
the result next to the source as `<name>-embedded.md`.
"""
import base64
import os
import re
import sys


def main(src_path):
    src_dir = os.path.dirname(os.path.abspath(src_path))
    text = open(src_path).read()

    def repl(m):
        alt, rel = m.group(1), m.group(2)
        p = os.path.join(src_dir, rel)
        if not os.path.exists(p):
            raise FileNotFoundError(f"missing figure: {rel}")
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        return f"![{alt}](data:image/png;base64,{b64})"

    out = re.sub(r"!\[([^\]]*)\]\((figs/[^)]+\.png)\)", repl, text)
    dst = src_path.replace(".md", "-embedded.md")
    open(dst, "w").write(out)
    n = len(re.findall(r"data:image/png;base64", out))
    print(f"{dst}: {n} images embedded, {len(out) // 1024} KiB")


if __name__ == "__main__":
    main(sys.argv[1])
