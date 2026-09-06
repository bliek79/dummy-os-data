from pathlib import Path

path = Path("scripts/prepare_alpha12_14.py")
text = path.read_text()
old = '    starts = [17 * 60] * 8 + [18 * 60] * 8\n'
new = '    starts = [17 * 60] * 8 + [17 * 60 + 45] * 8\n'
if old in text:
    path.write_text(text.replace(old, new, 1))
elif new not in text:
    raise AssertionError("instability fixture pattern not found")
