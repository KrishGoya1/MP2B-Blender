import re
fbx_path = r"c:\Users\Krish\Downloads\MP2B 01 BETA\MP2B 01 BETA\MP2B_Extension\mp2b_extension\mp2b_extension\Dummy.fbx"
with open(fbx_path, 'rb') as f:
    data = f.read()

# find all ascii strings >= 4 chars
matches = re.findall(b"[A-Za-z0-9_:\-]{4,}", data)
strings = sorted(list(set(m.decode('utf-8') for m in matches)))
bones = [s for s in strings if 'mixamorig' in s.lower() or 'bone' in s.lower() or 'head' in s.lower() or 'arm' in s.lower() or 'leg' in s.lower() or 'spine' in s.lower()]
for b in bones:
    print(b)
