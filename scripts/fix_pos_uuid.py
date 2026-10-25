#!/usr/bin/env python3
"""Run: python3 fix_pos_uuid.py /path/to/stockdesk-python (defaults to current directory)."""
import re
import sys
import os
from pathlib import Path

HELPER = '/** UUID v4 for request deduplication, including browsers on non-local HTTP origins. */\nexport function newRequestId(): string {\n  const source = globalThis.crypto;\n  if (typeof source?.randomUUID === "function") return source.randomUUID();\n  // getRandomValues is available on HTTP; randomUUID requires a secure context.\n  if (typeof source?.getRandomValues !== "function")\n    throw new Error(\n      "This browser cannot generate request IDs. Use a current browser.",\n    );\n  const bytes = source.getRandomValues(new Uint8Array(16));\n  bytes[6] = (bytes[6] & 0x0f) | 0x40;\n  bytes[8] = (bytes[8] & 0x3f) | 0x80;\n  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(\n    "",\n  );\n  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;\n}\n'
root=Path(sys.argv[1] if len(sys.argv)>1 else ".").resolve()
src=root/"frontend"/"src"
if not src.is_dir():
    raise SystemExit("Run from the StockDesk project root containing frontend/src, or supply that directory as the argument.")
helper=src/"requestId.ts"
if helper.exists() and helper.read_text()!=HELPER:
    raise SystemExit("requestId.ts already exists with different contents; review it before applying this patch.")
pattern=re.compile(r"(?<![\w.])(?:globalThis\.)?crypto\.randomUUID\(\)")
changed=[]
for file in src.rglob("*.tsx"):
    before=file.read_text()
    after,count=pattern.subn("newRequestId()",before)
    if not count: continue
    relative=os.path.relpath(helper.with_suffix(""),file.parent).replace(os.sep,"/")
    if not relative.startswith("."):relative="./"+relative
    statement='import { newRequestId } from "'+relative+'";'
    if statement not in after:after=statement+"\n"+after
    if file.name=="Workspace.tsx":
        after=after.replace('    if (pending.current?.signature !== signature)\n      pending.current = { signature, id: newRequestId() };\n    try {','    try {\n      if (pending.current?.signature !== signature)\n        pending.current = { signature, id: newRequestId() };')
    backup=root/"uuid-hotfix-backup"/file.relative_to(root)
    if backup.exists():
        raise SystemExit("An earlier backup exists for "+str(file)+"; inspect it before patching again.")
    changed.append((file,backup,before,after,count))
helper.write_text(HELPER)
for file,backup,before,after,count in changed:
    backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_text(before)
    file.write_text(after)
    print(f"Patched {file.relative_to(root)}: {count} call(s)")
print(f"Done: {sum(x[4] for x in changed)} call(s). Rebuild/recreate the frontend container, then hard-refresh the browser.")
