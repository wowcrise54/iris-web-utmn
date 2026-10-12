"""Compare retained uploaded files through read-only Docker mounts."""
import hashlib
import json
from pathlib import Path

report = {}
for folder in ('downloads', 'templates', 'server-data'):
    source = Path('/source') / folder
    target = Path('/target') / folder
    count = 0
    for file in source.rglob('*'):
        if not file.is_file() or file.is_symlink():
            continue
        copy = target / file.relative_to(source)
        assert copy.is_file(), f'Missing saved file in {folder}'
        assert hashlib.file_digest(file.open('rb'), 'sha256').digest() == hashlib.file_digest(copy.open('rb'), 'sha256').digest(), \
            f'File changed in {folder}'
        count += 1
    report[folder] = {'saved_files': count, 'hashes_match': True}
print(json.dumps(report, indent=2))
