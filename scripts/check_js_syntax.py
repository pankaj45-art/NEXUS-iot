"""Check syntax balance of JS files."""
import sys
from pathlib import Path

content = Path("web/app.js").read_text(encoding="utf-8")

# Check backtick count
lines = content.splitlines()
print(f"Total lines: {len(lines)}")

# Check brace balance outside strings/comments
# A simple tokenizer:
stack = []
in_single = False
in_double = False
in_template = 0
in_line_comment = False
in_block_comment = False
escaped = False

errors = []
for line_no, line in enumerate(lines, 1):
    i = 0
    while i < len(line):
        c = line[i]
        
        if in_line_comment:
            break
        if in_block_comment:
            if c == '*' and i + 1 < len(line) and line[i+1] == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
            
        if escaped:
            escaped = False
            i += 1
            continue
            
        if c == '\\':
            escaped = True
            i += 1
            continue
            
        if in_single:
            if c == "'": in_single = False
            i += 1
            continue
        if in_double:
            if c == '"': in_double = False
            i += 1
            continue
            
        # Comments
        if c == '/' and i + 1 < len(line):
            if line[i+1] == '/':
                in_line_comment = True
                break
            elif line[i+1] == '*':
                in_block_comment = True
                i += 2
                continue
                
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == '`':
            if in_template:
                in_template -= 1
            else:
                in_template += 1
            i += 1
            continue
            
        if in_template:
            # Check for ${ inside template
            if c == '$' and i + 1 < len(line) and line[i+1] == '{':
                stack.append(('${', line_no))
                i += 2
                continue
                
        if c in '({[':
            stack.append((c, line_no))
        elif c in ')}]':
            if not stack:
                errors.append(f"Unmatched closing '{c}' at line {line_no}")
            else:
                top, top_line = stack.pop()
                expected = {'(': ')', '{': '}', '[': ']', '${': '}'}[top]
                if c != expected:
                    errors.append(f"Mismatched '{c}' at line {line_no}, expected '{expected}' (opened at line {top_line})")
        i += 1
    in_line_comment = False

print(f"Stack remaining: {len(stack)}")
for item in stack[-10:]:
    print(f"  Unclosed: {item[0]} from line {item[1]}")
if errors:
    print("Errors found:")
    for err in errors[:10]:
        print(f"  {err}")
else:
    print("No bracket balance errors!")
