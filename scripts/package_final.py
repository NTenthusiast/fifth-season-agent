"""保留原提交包文件布局，合入决赛代码与答辩材料。"""
from pathlib import Path
import zipfile
import hashlib

root = Path(__file__).resolve().parents[1]
original = root.parent / '第五个季节.zip'
output = root / '决赛材料' / '第五个季节_决赛完整版.zip'
files = {}
with zipfile.ZipFile(original) as source:
    for name in source.namelist():
        if not name.endswith('/'):
            local = root / name
            files[name] = local.read_bytes() if local.is_file() else source.read(name)
for folder in ['src', 'config', 'assets', 'scripts']:
    for path in (root / folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            files[path.relative_to(root).as_posix()] = path.read_bytes()
for pattern in ['决赛材料/*.pptx', '决赛材料/*.docx', '决赛材料/*.doc', '决赛材料/*.txt', 'docs/真实试点方案.md']:
    for path in root.glob(pattern):
        files[path.relative_to(root).as_posix()] = path.read_bytes()
for name in ['README.md', 'AGENT.md']:
    files[name] = (root / name).read_bytes()
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
    for name, content in sorted(files.items()):
        target.writestr(name, content)
with zipfile.ZipFile(output) as target:
    assert target.testzip() is None
    for name, content in files.items():
        assert target.read(name) == content
print(f'压缩包校验通过：{len(files)} 个文件，{output.stat().st_size} 字节')
print(hashlib.sha256(output.read_bytes()).hexdigest())
